"""实例生命周期操作：入队与状态前置校验。

用户操作先创建任务再异步执行，观测状态只在查询 libvirt 后更新。
"""

import logging

from apps.instances.models import DesiredState, Instance, ObservedState
from apps.tasks.models import TaskType
from apps.tasks.services import enqueue
from common.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)

# 动作到任务类型的映射，集中维护
ACTION_TASK_TYPES = {
    'start': TaskType.INSTANCE_START,
    'shutdown': TaskType.INSTANCE_SHUTDOWN,
    'force-stop': TaskType.INSTANCE_FORCE_STOP,
    'reboot': TaskType.INSTANCE_REBOOT,
}


def start_action(instance: Instance, user, action: str):
    """为生命周期动作创建任务。

    Args:
        instance: 目标实例。
        user: 发起人。
        action: start / shutdown / force-stop / reboot。

    Returns:
        任务对象；已处于目标状态时返回 None（幂等）。

    Raises:
        AppError: 动作未知、状态不允许或节点离线。
    """
    task_type = ACTION_TASK_TYPES.get(action)
    if task_type is None:
        raise AppError(ErrorCode.INVALID_ARGUMENT, '不支持的操作')

    if not instance.node.is_schedulable:
        raise AppError(
            ErrorCode.NODE_OFFLINE,
            '节点不可用',
            details={'node': [f'当前状态为 {instance.node.status}']},
        )

    if action == 'start' and instance.observed_state == ObservedState.RUNNING:
        logger.info('实例已在运行，按幂等返回', extra={'instance_id': instance.pk})
        return None

    if action in {'shutdown', 'reboot'} and instance.observed_state == ObservedState.SHUTOFF:
        raise AppError(
            ErrorCode.CONFLICT,
            '实例未运行',
            details={'observed_state': instance.observed_state},
        )

    if instance.operation_status in {'PENDING', 'VALIDATING', 'PREPARING', 'CREATING', 'VERIFYING'}:
        raise AppError(
            ErrorCode.OPERATION_IN_PROGRESS,
            '实例存在未结束的任务',
            details={'operation_status': instance.operation_status},
        )

    task = enqueue(
        task_type=task_type,
        resource_type='instance',
        resource_id=str(instance.pk),
        requested_by=user,
        payload={'action': action, 'domain_name': instance.libvirt_domain_name},
        max_attempts=2,
    )

    instance.current_task = task
    instance.operation_status = 'PENDING'
    if action == 'start':
        instance.desired_state = DesiredState.RUNNING
    elif action == 'shutdown':
        instance.desired_state = DesiredState.SHUTOFF
    instance.save(update_fields=['current_task', 'operation_status', 'desired_state', 'updated_at'])
    return task


def request_delete(instance: Instance, user, *, purge_disk: bool):
    """创建删除任务。

    Args:
        instance: 目标实例。
        user: 发起人。
        purge_disk: 是否同时删除磁盘文件。

    Returns:
        任务对象。
    """
    if instance.operation_status in {'PENDING', 'VALIDATING', 'PREPARING', 'CREATING', 'VERIFYING'}:
        raise AppError(
            ErrorCode.OPERATION_IN_PROGRESS,
            '实例存在未结束的任务',
            details={'operation_status': instance.operation_status},
        )

    disk = instance.disks.filter(role='SYSTEM').first()
    task = enqueue(
        task_type=TaskType.INSTANCE_DELETE,
        resource_type='instance',
        resource_id=str(instance.pk),
        requested_by=user,
        payload={
            'domain_name': instance.libvirt_domain_name,
            'purge_disk': purge_disk,
            'disk_relative_path': disk.relative_path if disk else '',
        },
        max_attempts=2,
    )
    instance.current_task = task
    instance.operation_status = 'PENDING'
    instance.save(update_fields=['current_task', 'operation_status', 'updated_at'])
    return task
