"""Worker operations report only acknowledged Agent results."""

from urllib.parse import quote

from django.shortcuts import get_object_or_404

from apps.audit.services import record_audit
from apps.instances.models import Instance
from apps.nodes.client import AgentClient
from apps.nodes.models import Node
from common.errors import AppError, ErrorCode


def execute_infrastructure(task):
    if task.type == 'STORAGE_POOL_CREATE':
        node = get_object_or_404(Node, pk=task.resource_id, is_deleted=False)
        path = '/api/v1/storage-pools'
    else:
        instance = get_object_or_404(
            Instance.objects.select_related('node'), pk=task.resource_id, is_deleted=False
        )
        node = instance.node
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
