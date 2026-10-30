"""Worker operations report only acknowledged Agent results."""

from urllib.parse import quote

from django.db import transaction
from django.shortcuts import get_object_or_404

from apps.audit.services import record_audit
from apps.instances.models import Instance
from apps.nodes.client import AgentClient
from apps.nodes.models import Node
from common.errors import AppError, ErrorCode


@transaction.atomic
def execute_infrastructure(task):
    if task.type == 'STORAGE_POOL_CREATE':
        node = get_object_or_404(Node, pk=task.resource_id, is_deleted=False)
        path = '/api/v1/storage-pools'
    else:
        instance = get_object_or_404(
            Instance.objects.select_related('node'), pk=task.resource_id, is_deleted=False
        )
        node = Node.objects.select_for_update().get(pk=instance.node_id)
        instance = Instance.objects.select_for_update().get(pk=instance.pk, is_deleted=False)
        from common.permissions import check_permission
        from common.scope import instances_for

        if (
            not task.requested_by
            or not instances_for(task.requested_by).filter(pk=instance.pk).exists()
        ):
            raise AppError(ErrorCode.PERMISSION_DENIED)
        check_permission(
            task.requested_by,
            'instances.manage_snapshot_instance',
            target_type='instance',
            target_id=str(instance.pk),
        )
        if instance.observed_state != 'SHUTOFF' or instance.observed_state_is_stale:
            raise AppError(ErrorCode.CONFLICT, '请先正常关机并等待状态同步后操作快照')
        path = f'/api/v1/domains/{quote(instance.libvirt_domain_name, safe="")}/snapshots'
    if not node.is_schedulable:
        raise AppError(ErrorCode.NODE_OFFLINE)
    result = AgentClient(node.endpoint, timeout=180).request_json(path, 'POST', task.payload)
    record_audit(
        action=task.type + '_COMPLETED',
        actor=task.requested_by,
        target_type=task.resource_type,
        target_id=task.resource_id,
        task_id=str(task.pk),
    )
    return result
