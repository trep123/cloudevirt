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
        node = get_object_or_404(
            Node.objects.select_for_update(), pk=task.resource_id, is_deleted=False
        )
        path = '/api/v1/storage-pools'
        agent_payload = {key: task.payload[key] for key in ('name', 'path') if key in task.payload}
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
        pool_name = instance.storage_pool.name if instance.storage_pool_id else ''
        if pool_name:
            path += f'?storage_pool={quote(pool_name, safe="")}'
        agent_payload = task.payload
    if not node.is_schedulable:
        raise AppError(ErrorCode.NODE_OFFLINE)
    client = AgentClient(node.endpoint, timeout=180)
    result = client.request_json(path, 'POST', agent_payload)
    if task.type == 'STORAGE_POOL_CREATE':
        from apps.infrastructure.models import ManagedStoragePool

        listing = client.get_json('/api/v1/storage-pools')
        actual = next(
            (
                item
                for item in listing.get('results', [])
                if item.get('name') == task.payload['name']
            ),
            None,
        )
        if not actual or actual.get('type') != 'dir' or not actual.get('active'):
            raise AppError(ErrorCode.CONFLICT, '节点未确认目录存储池已激活')
        actual_path = actual.get('target', {}).get('path', '')
        if task.payload.get('path') and actual_path != task.payload['path']:
            raise AppError(ErrorCode.CONFLICT, '节点存储池路径与创建请求不一致')
        pool, created = ManagedStoragePool.objects.get_or_create(
            node=node, name=task.payload['name'], defaults={'path': actual_path}
        )
        if not created and pool.path != actual_path:
            raise AppError(ErrorCode.CONFLICT, '已有同名存储池路径不同')
        if task.payload.get('is_default'):
            ManagedStoragePool.objects.filter(node=node, is_default=True).exclude(
                pk=pool.pk
            ).update(is_default=False)
            pool.is_default = True
            pool.save(update_fields=['is_default'])
        pool.allowed_users.set(task.payload.get('assigned_user_ids', []))
        default_ids = task.payload.get('default_user_ids', [])
        for other in ManagedStoragePool.objects.filter(node=node).exclude(pk=pool.pk):
            other.default_users.remove(*default_ids)
        pool.default_users.set(default_ids)
    record_audit(
        action=task.type + '_COMPLETED',
        actor=task.requested_by,
        target_type=task.resource_type,
        target_id=task.resource_id,
        task_id=str(task.pk),
    )
    return result
