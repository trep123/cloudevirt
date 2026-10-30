"""实例相关任务执行器。

创建流程：置为 CREATING → 调用 Agent 创建域 → 回读确认 → 提交预留；
失败时记录错误并释放预留（仅在确认资源未创建时）。
"""

import logging
import time

from django.conf import settings
from django.utils import timezone

from apps.instances.hardware import validate_creation_capabilities
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
    from django.contrib.auth import get_user_model

    from apps.accounts.administration import limit_nodes

    actor = get_user_model().objects.filter(pk=task.requested_by_id, is_active=True).first()
    if (
        actor is None
        or not actor.has_perm('instances.add_instance')
        or instance.created_by_id != actor.pk
        or instance.node_id not in limit_nodes(actor, {instance.node_id}, 'instances.add_instance')
    ):
        raise AppError(ErrorCode.PERMISSION_DENIED, '创建任务的用户授权已失效，请重新提交')

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
        'network_type': (task.payload or {}).get('network_type', ''),
        'network_bridge': (task.payload or {}).get('network_bridge', ''),
        'vlan_id': (task.payload or {}).get('vlan_id') or 0,
        'vnc_password': instance.vnc_password,
    }
    client = AgentClient(instance.node.endpoint)
    creation_requested = False
    try:
        config = instance.creation_config or {}
        if config.get('source_disk'):
            from apps.instances.disk_sources import source_disk

            retained = source_disk(actor, config['source_disk']['id'], instance.node_id)
            if retained.relative_path != config['source_disk']['relative_path']:
                raise AppError(ErrorCode.CONFLICT, '源磁盘路径已变化')
        source = config.get('image') or (
            {
                'relative_path': instance.image.relative_path,
                'format': instance.image.format,
                'checksum': instance.image.checksum_sha256,
            }
            if instance.image
            else {'relative_path': '', 'format': '', 'checksum': ''}
        )
        capabilities = client.get_json('/api/v1/node/capabilities')
        validate_creation_capabilities(config, capabilities)
        if not all(
            capabilities.get(key) is True for key in ['image_clone', 'iso_install', 'start_control']
        ):
            raise AppError(ErrorCode.CONFLICT, '节点 Agent 需要升级后才能可靠创建镜像虚拟机')
        payload.update(
            hardware=config.get('hardware', {}),
            initialization={
                **config['initialization'],
                'networks': config.get('guest_networks', []),
            }
            if config.get('initialization')
            else None,
            mac=config.get('primary_mac', ''),
            data_disks=[
                {'relative_path': d.relative_path, 'size_gib': d.size_gib}
                for d in instance.disks.filter(role='DATA').order_by('target_dev')
            ],
            additional_networks=config.get('network_specs', []),
            image_relative_path=source['relative_path'],
            image_format=source['format'],
            image_checksum=source['checksum'],
            start_after_create=config.get('start_after_create', True),
            autostart=instance.autostart,
        )
        if config.get('source_disk'):
            if capabilities.get('retained_disk_clone') is not True:
                raise AppError(ErrorCode.CONFLICT, '节点需升级以支持已有系统盘克隆')
            payload.update(
                source_disk_relative_path=config['source_disk']['relative_path'],
                image_relative_path='',
                image_format='',
                image_checksum='',
            )
        if config.get('existing_system_file'):
            from apps.accounts.administration import require_admin

            require_admin(actor, 'instances.add_instance')
            if capabilities.get('existing_disk_attach') is not True:
                raise AppError(ErrorCode.CONFLICT, '节点需升级以支持直接使用系统盘')
            payload.update(
                use_existing_disk=True, image_relative_path='', image_format='', image_checksum=''
            )
        creation_requested = True
        result = client.create_domain(payload)
        if (
            config.get('start_after_create', True)
            and normalize_state(str(result.get('state') or '')) != ObservedState.RUNNING
        ):
            raise AppError(
                ErrorCode.OPERATION_FAILED,
                '节点未确认虚拟机运行，创建启动阶段失败，请检查 libvirt 日志',
            )
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
        # A failed response can occur after disks/domain creation. Reconcile before releasing.
        record_event(
            task,
            from_status=task.status,
            to_status=task.status,
            message='创建结果需核对，保留资源预留以避免重复分配',
        )
        if not creation_requested:
            release_reservation(instance)
        logger.error(
            '实例创建失败',
            extra={'instance_id': instance.pk, 'error_code': exc.code},
        )
        raise

    instance.mark_observed(normalize_state(str(result.get('state') or '')))
    if config.get('initialization'):
        instance.initialization_status = (
            'DELIVERED' if result.get('initialization_delivered') else 'UNKNOWN'
        )
        instance.save(update_fields=['initialization_status'])
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

    instance.disks.filter(role='DATA').update(status=DiskStatus.READY)
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
        if action == 'start' and state != ObservedState.RUNNING:
            raise AppError(
                ErrorCode.OPERATION_FAILED, '节点未确认虚拟机运行，启动任务不能标记为成功'
            )
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
    live_disks = instance.disks.exclude(status='DELETED')
    if purge_disk and live_disks.filter(role='DATA').exists():
        result = client.delete_domain_disks(
            instance.libvirt_domain_name,
            list(live_disks.values_list('relative_path', flat=True)),
        )
    else:
        result = client.delete_domain(
            instance.libvirt_domain_name, disk_relative_path if purge_disk else ''
        )

    if purge_disk and live_disks.exists() and result.get('disk_removed') is not True:
        raise AppError(ErrorCode.CONFLICT, '节点未确认关联磁盘清理完成，请核对任务后重试')
    instance.is_deleted = True
    from apps.networks.models import IPLease

    IPLease.objects.filter(nic__instance=instance, active=True).update(active=False)
    instance.disks_deleted = purge_disk
    instance.operation_status = 'SUCCEEDED'
    instance.save(update_fields=['is_deleted', 'disks_deleted', 'operation_status', 'updated_at'])

    for item in live_disks:
        item.status = DiskStatus.DELETED if purge_disk else DiskStatus.READY
        item.is_orphan = not purge_disk
        item.save(update_fields=['status', 'is_orphan', 'updated_at'])

    # 删除后资源释放，预留从已分配转为已释放
    ResourceReservation.objects.filter(instance=instance).update(
        status='RELEASED', updated_at=timezone.now()
    )
    return {
        'instance_id': instance.pk,
        'deleted': True,
        'disk_removed': bool(result.get('disk_removed', False)),
    }
