"""����ִ����ע�����

��ҵ��ģ���ڴ˵Ǽ��Լ���ִ������δ�Ǽǵ����ͻᱻ��ȷʧ�ܣ�
���⡰������ӵ�û��ʵ�֡��ľ�Ĭ�ɹ���
"""

import logging

from apps.accounts.bulk import execute_account_batch
from apps.images.uploads import execute_image_import
from apps.infrastructure.executors import execute_infrastructure
from apps.instances.display import execute_instance_display
from apps.instances.executors import (
    execute_instance_action,
    execute_instance_create,
    execute_instance_delete,
)
from apps.nodes.models import Node
from apps.nodes.services import refresh_node
from apps.tasks.models import Task, TaskStatus, TaskType
from apps.tasks.services import record_event
from common.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)


def execute_node_refresh(task: Task) -> dict:
    """ִ�нڵ���Դˢ�¡�

    Args:
        task: �������resource_id Ϊ�ڵ�������

    Returns:
        ִ�н��ժҪ��

    Raises:
        AppError: �ڵ㲻����ʱ�׳� NOT_FOUND��
    """
    node = Node.objects.filter(pk=task.resource_id, is_deleted=False).first()
    if node is None:
        raise AppError(ErrorCode.NOT_FOUND, '�ڵ㲻����')
    record_event(task, to_status=TaskStatus.PREPARING, message='��ʼ�ɼ��ڵ���Դ')
    refresh_node(node)
    if node.status == 'OFFLINE':
        raise AppError(ErrorCode.NODE_OFFLINE, '�ڵ����ߣ��ɼ�δ���')
    return {'node_id': node.pk, 'status': node.status, 'cpu_total': node.cpu_total}


EXECUTORS = {
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
    """�����ͷַ�ִ�С�

    Args:
        task: ��ִ������

    Returns:
        ִ�н���ֵ䡣

    Raises:
        AppError: ����δ�Ǽ�ִ����ʱ�׳� OPERATION_FAILED��
    """
    executor = EXECUTORS.get(task.type)
    if executor is None:
        raise AppError(ErrorCode.OPERATION_FAILED, f'��������δ�Ǽ�ִ����: {task.type}')
    return executor(task)
