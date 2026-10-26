"""实例相关任务执行器。

创建流程：置为 CREATING → 调用 Agent 创建域 → 回读确认 → 提交预留；
失败时记录错误并释放预留（仅在确认资源未创建时）。
"""

import logging

from apps.instances.models import DiskStatus, Instance, ObservedState
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
