"""任务执行器注册表。

各业务模块在此登记自己的执行器；未登记的类型会被明确失败，
避免“任务入队但没有实现”的静默成功。
"""

import logging

from apps.accounts.bulk import execute_account_batch
from apps.images.uploads import execute_image_import
from apps.infrastructure.executors import execute_infrastructure
from apps.instances.device_management import execute_hardware_change
from apps.instances.disk_cleanup import execute_disk_delete
from apps.instances.display import execute_instance_display
from apps.instances.executors import (
    execute_instance_action,
    execute_instance_create,
    execute_instance_delete,
)
from apps.networks.bridges import execute_bridge
from apps.nodes.models import Node
from apps.nodes.services import refresh_node
from apps.tasks.models import Task, TaskStatus, TaskType
from apps.tasks.services import record_event
from common.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)


def execute_node_refresh(task: Task) -> dict:
    """执行节点资源刷新。

    Args:
        task: 任务对象，resource_id 为节点主键。

    Returns:
        执行结果摘要。

    Raises:
        AppError: 节点不存在时抛出 NOT_FOUND。
    """
    node = Node.objects.filter(pk=task.resource_id, is_deleted=False).first()
    if node is None:
        raise AppError(ErrorCode.NOT_FOUND, '节点不存在')
    record_event(task, to_status=TaskStatus.PREPARING, message='开始采集节点资源')
    refresh_node(node)
    if node.status == 'OFFLINE':
        raise AppError(ErrorCode.NODE_OFFLINE, '节点离线，采集未完成')
    return {'node_id': node.pk, 'status': node.status, 'cpu_total': node.cpu_total}


EXECUTORS = {
    'DISK_DELETE': execute_disk_delete,
    'NETWORK_BRIDGE_CREATE': execute_bridge,
    TaskType.INSTANCE_HARDWARE: execute_hardware_change,
    TaskType.INSTANCE_DISPLAY: execute_instance_display,
    TaskType.ACCOUNT_BATCH: execute_account_batch,
    TaskType.IMAGE_IMPORT: execute_image_import,
    'STORAGE_POOL_CREATE': execute_infrastructure,
    'INSTANCE_SNAPSHOT': execute_infrastructure,
    TaskType.NODE_REFRESH: execute_node_refresh,
    TaskType.INSTANCE_CREATE: execute_instance_create,
    TaskType.INSTANCE_START: execute_instance_action,
    TaskType.INSTANCE_SHUTDOWN: execute_instance_action,
    TaskType.INSTANCE_FORCE_STOP: execute_instance_action,
    TaskType.INSTANCE_REBOOT: execute_instance_action,
    TaskType.INSTANCE_DELETE: execute_instance_delete,
}


def execute_task(task: Task) -> dict:
    """按类型分发执行。

    Args:
        task: 待执行任务。

    Returns:
        执行结果字典。

    Raises:
        AppError: 类型未登记执行器时抛出 OPERATION_FAILED。
    """
    executor = EXECUTORS.get(task.type)
    if executor is None:
        raise AppError(ErrorCode.OPERATION_FAILED, f'任务类型未登记执行器: {task.type}')
    return executor(task)
