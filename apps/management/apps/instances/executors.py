"""实例相关任务执行器。

创建流程：置为 CREATING → 调用 Agent 创建域 → 回读确认 → 提交预留；
失败时记录错误并释放预留（仅在确认资源未创建时）。
"""

import logging
import time

from django.conf import settings
from django.utils import timezone

from apps.instances.models import (
    DiskStatus,
    Instance,
    ObservedState,
    ResourceReservation,
)
from apps.instances.services import commit_reservation, release_reservation
from apps.nodes.client import AgentClient
from apps.tasks.models import Task, TaskStatus
from apps.tasks.services import record_event
from common.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)


def normalize_state(raw_state: str) -> str:
    """把 Agent 返回的状态映射为平台观测状态，未知一律 UNKNOWN。"""
    value = (raw_state or '').upper()
    if value in ObservedState.values:
        return value
    return ObservedState.UNKNOWN


def execute_instance_create(task: Task) -> dict:
    """执行实例创建任务。

    Args:
        task: 任务对象，resource_id 为实例主键。

    Returns:
        执行结果摘要。

    Raises:
        AppError: 实例不存在或 Agent 创建失败。
    """
    instance = (
        Instance.objects.select_related('node', 'image')
        .filter(pk=task.resource_id, is_deleted=False)
        .first()
    )
    if instance is None:
        raise AppError(ErrorCode.NOT_FOUND, '实例不存在')

    disk = instance.disks.filter(role='SYSTEM').first()
    if disk is None:
        raise AppError(ErrorCode.OPERATION_FAILED, '实例缺少系统盘记录')

    task.status = TaskStatus.CREATING
    task.save(update_fields=['status', 'updated_at'])
    instance.operation_status = 'CREATING'
    instance.save(update_fields=['operation_status', 'updated_at'])
    record_event(
        task,
        from_status=TaskStatus.VALIDATING,
        to_status=TaskStatus.CREATING,
        message='开始调用节点创建域',
    )

    payload = {
        'name': instance.libvirt_domain_name,
        'uuid': str(instance.uuid),
        'vcpu': instance.vcpu,
        'memory_mib': instance.memory_mib,
        'disk_relative_path': disk.relative_path,
        'disk_gib': instance.disk_gib,
        'network': instance.network_name,
        'vnc_password': instance.vnc_password,
    }
    client = AgentClient(instance.node.endpoint)
    try:
        result = client.create_domain(payload)
    except AppError as exc:
        instance.operation_status = 'FAILED'
        instance.last_error_code = exc.code
        instance.last_error_message = exc.message
        instance.save(
            update_fields=[
                'operation_status',
                'last_error_code',
                'last_error_message',
                'updated_at',
            ]
        )
        disk.status = DiskStatus.FAILED
        disk.save(update_fields=['status', 'updated_at'])
        # Agent 明确失败时资源未创建，释放预留以便重试或他人使用
        release_reservation(instance)
        logger.error(
            '实例创建失败',
            extra={'instance_id': instance.pk, 'error_code': exc.code},
        )
        raise

    instance.mark_observed(normalize_state(str(result.get('state') or '')))
    instance.operation_status = 'SUCCEEDED'
    instance.last_error_code = ''
    instance.last_error_message = ''
    instance.save(
        update_fields=[
            'observed_state',
            'observed_state_updated_at',
            'observed_state_is_stale',
            'operation_status',
            'last_error_code',
            'last_error_message',
            'updated_at',
        ]
    )

    disk.status = DiskStatus.READY
    disk.virtual_size_bytes = (
        result.get('disk_virtual_size_bytes') or disk.size_gib * 1024 * 1024 * 1024
    )
    disk.save(update_fields=['status', 'virtual_size_bytes', 'updated_at'])
    commit_reservation(instance)

    logger.info(
        '实例创建成功',
        extra={'instance_id': instance.pk, 'state': instance.observed_state},
    )
    return {
        'instance_id': instance.pk,
        'uuid': str(instance.uuid),
        'state': instance.observed_state,
        'created': bool(result.get('created', True)),
    }


def wait_for_state(
    client, name: str, expected: set[str], timeout_seconds: int, interval_seconds: float
):
    """轮询域状态直到达到期望状态或超时。

    Args:
        client: Agent 客户端。
        name: 域名。
        expected: 可接受的归一化状态集合。
        timeout_seconds: 超时秒数。
        interval_seconds: 轮询间隔。

    Returns:
        最后一次观测到的状态。
    """
    deadline = time.monotonic() + timeout_seconds
    state = ObservedState.UNKNOWN
    while time.monotonic() < deadline:
        domains = client.domains()
        for item in domains:
            if item.get('name') == name:
                state = normalize_state(str(item.get('state') or ''))
                break
        if state in expected:
            return state
        time.sleep(interval_seconds)
    return state


def _record_failure(instance: Instance, error: AppError) -> None:
    """把失败记录到实例，供前端展示。"""
    instance.operation_status = 'FAILED'
    instance.last_error_code = error.code
    instance.last_error_message = error.message
    instance.save(
        update_fields=[
            'operation_status',
            'last_error_code',
            'last_error_message',
            'updated_at',
        ]
    )


ACTION_NAMES = {
    'INSTANCE_START': 'start',
    'INSTANCE_SHUTDOWN': 'shutdown',
    'INSTANCE_FORCE_STOP': 'force-stop',
    'INSTANCE_REBOOT': 'reboot',
}


def execute_instance_action(task: Task) -> dict:
    """执行启动/关机/强停/重启任务。

    Args:
        task: 任务对象。

    Returns:
        执行结果摘要。
    """
    instance = (
        Instance.objects.select_related('node')
        .filter(pk=task.resource_id, is_deleted=False)
        .first()
    )
    if instance is None:
        raise AppError(ErrorCode.NOT_FOUND, '实例不存在')

    action = ACTION_NAMES[task.type]
    task.status = TaskStatus.PREPARING
    task.save(update_fields=['status', 'updated_at'])
    instance.operation_status = 'PREPARING'
    instance.save(update_fields=['operation_status', 'updated_at'])

    client = AgentClient(instance.node.endpoint)
    try:
        result = client.domain_action(instance.libvirt_domain_name, action)
        state = normalize_state(str(result.get('state') or ''))
        if action in {'shutdown', 'force-stop'} and state != ObservedState.SHUTOFF:
            state = wait_for_state(
                client,
                instance.libvirt_domain_name,
                {ObservedState.SHUTOFF},
                int(getattr(settings, 'INSTANCE_SHUTDOWN_TIMEOUT_SECONDS', 60)),
                float(getattr(settings, 'INSTANCE_STATE_POLL_INTERVAL_SECONDS', 2)),
            )
        if action in {'shutdown', 'force-stop'} and state != ObservedState.SHUTOFF:
            # 超时不自动强停，交由用户显式选择
            raise AppError(ErrorCode.OPERATION_FAILED, '关机超时，可选择强制停止')
    except AppError as exc:
        _record_failure(instance, exc)
        logger.error(
            '实例操作失败',
            extra={'instance_id': instance.pk, 'action': action, 'error_code': exc.code},
        )
        raise

    instance.mark_observed(state)
    instance.operation_status = 'SUCCEEDED'
    instance.last_error_code = ''
    instance.last_error_message = ''
    instance.save(
        update_fields=[
            'observed_state',
            'observed_state_updated_at',
            'observed_state_is_stale',
            'operation_status',
            'last_error_code',
            'last_error_message',
            'updated_at',
        ]
    )
    return {'instance_id': instance.pk, 'action': action, 'state': instance.observed_state}


def execute_instance_delete(task: Task) -> dict:
    """执行删除任务：销毁域、按选择删除磁盘、释放资源。"""
    instance = Instance.objects.select_related('node').filter(pk=task.resource_id).first()
    if instance is None:
        raise AppError(ErrorCode.NOT_FOUND, '实例不存在')

    payload = task.payload or {}
    purge_disk = bool(payload.get('purge_disk', False))
    disk = instance.disks.filter(role='SYSTEM').first()
    disk_relative_path = payload.get('disk_relative_path') or (disk.relative_path if disk else '')

    client = AgentClient(instance.node.endpoint)
    result = client.delete_domain(
        instance.libvirt_domain_name, disk_relative_path if purge_disk else ''
    )

    instance.is_deleted = True
    instance.disks_deleted = purge_disk
    instance.operation_status = 'SUCCEEDED'
    instance.save(update_fields=['is_deleted', 'disks_deleted', 'operation_status', 'updated_at'])

    for item in instance.disks.all():
        item.status = DiskStatus.DELETED
        item.save(update_fields=['status', 'updated_at'])

    # 删除后资源释放，预留从已分配转为已释放
    ResourceReservation.objects.filter(instance=instance).update(
        status='RELEASED', updated_at=timezone.now()
    )
    return {
        'instance_id': instance.pk,
        'deleted': True,
        'disk_removed': bool(result.get('disk_removed', False)),
    }
