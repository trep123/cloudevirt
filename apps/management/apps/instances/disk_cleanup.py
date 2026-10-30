"""Retained disk visibility and task-backed deletion with ownership checks."""

import hashlib

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.administration import limit_nodes
from apps.accounts.roles import is_admin
from apps.audit.services import record_audit
from apps.instances.actions import ensure_no_active_task
from apps.instances.models import Disk, Instance
from apps.nodes.access import accessible_node_ids
from apps.nodes.client import AgentClient
from apps.nodes.models import Node
from apps.tasks.models import Task
from apps.tasks.services import enqueue
from common.errors import AppError, ErrorCode
from common.permissions import RequiresPasswordChange, check_permission


def disks_for(user):
    query = Disk.objects.select_related('instance', 'instance__node')
    if is_admin(user):
        return query
    return query.filter(
        instance__created_by=user,
        instance__node_id__in=limit_nodes(
            user, accessible_node_ids(user), 'instances.view_instance'
        ),
    )


def eligible(disk):
    from apps.instances.disk_sources import cloning

    return (
        not cloning(disk.pk)
        and disk.status != 'DELETED'
        and disk.is_orphan
        and (disk.instance.is_deleted or disk.status == 'DETACHED')
    )


def task_response(task):
    return Response({'task_id': str(task.pk), 'status': task.status}, status=202)


class DiskDeleteView(APIView):
    permission_classes = [IsAuthenticated, RequiresPasswordChange]

    @transaction.atomic
    def delete(self, request, pk):
        visible = get_object_or_404(disks_for(request.user), pk=pk)
        Node.objects.select_for_update().get(pk=visible.instance.node_id)
        instance = Instance.objects.select_for_update().get(pk=visible.instance_id)
        disk = Disk.objects.select_for_update().select_related('instance').get(pk=pk)
        check_permission(
            request.user,
            'instances.delete_disk_instance',
            target_type='instance',
            target_id=str(instance.pk),
        )
        key = request.headers.get('Idempotency-Key', '')
        if not key or len(key) > 128:
            raise AppError(ErrorCode.INVALID_ARGUMENT, '请提供不超过 128 字符的幂等键')
        digest = hashlib.sha256(f'disk-delete:{request.user.pk}:{key}'.encode()).hexdigest()
        previous = Task.objects.filter(idempotency_key=digest).first()
        if previous:
            if previous.type != 'DISK_DELETE' or previous.payload.get('disk_id') != pk:
                raise AppError(ErrorCode.CONFLICT, '幂等键已用于不同磁盘')
            return task_response(previous)
        if not eligible(disk):
            raise AppError(ErrorCode.CONFLICT, '仅可删除已保留或已卸载且未被引用的磁盘')
        ensure_no_active_task(instance)
        task = enqueue(
            task_type='DISK_DELETE',
            resource_type='instance',
            resource_id=str(instance.pk),
            requested_by=request.user,
            payload={'disk_id': pk, 'relative_path': disk.relative_path},
            idempotency_key=digest,
            max_attempts=1,
        )
        record_audit(
            action='DISK_DELETE',
            actor=request.user,
            target_type='disk',
            target_id=str(pk),
            task_id=str(task.pk),
            details={'path': disk.relative_path, 'instance': instance.pk},
        )
        return task_response(task)


@transaction.atomic
def execute_disk_delete(task):
    visible = get_object_or_404(
        Disk.objects.select_related('instance'),
        pk=task.payload['disk_id'],
        instance_id=task.resource_id,
    )
    node = Node.objects.select_for_update().get(pk=visible.instance.node_id)
    instance = Instance.objects.select_for_update().get(pk=visible.instance_id)
    disk = Disk.objects.select_for_update().select_related('instance').get(pk=visible.pk)
    user = task.requested_by
    if not user or not disks_for(user).filter(pk=disk.pk).exists():
        raise AppError(ErrorCode.PERMISSION_DENIED)
    check_permission(
        user, 'instances.delete_disk_instance', target_type='instance', target_id=str(instance.pk)
    )
    if disk.status == 'DELETED':
        return {'disk_id': disk.pk, 'deleted': True}
    if not eligible(disk) or task.payload.get('relative_path') != disk.relative_path:
        raise AppError(ErrorCode.CONFLICT, '磁盘状态或路径已变化，停止删除')
    if not node.is_schedulable:
        raise AppError(ErrorCode.NODE_OFFLINE)
    result = AgentClient(node.endpoint, timeout=180).request_json(
        '/api/v1/disks', 'DELETE', {
            'relative_path': disk.relative_path,
            'storage_pool': instance.storage_pool.name if instance.storage_pool_id else '',
        }
    )
    if (
        not isinstance(result, dict)
        or result.get('deleted') is not True
        or result.get('relative_path') != disk.relative_path
    ):
        raise AppError(ErrorCode.CONFLICT, '节点未确认磁盘删除，请核对后重试')
    disk.status = 'DELETED'
    disk.is_orphan = False
    disk.actual_size_bytes = 0
    disk.save(update_fields=['status', 'is_orphan', 'actual_size_bytes', 'updated_at'])
    if instance.is_deleted and not instance.disks.exclude(status='DELETED').exists():
        instance.disks_deleted = True
        instance.save(update_fields=['disks_deleted', 'updated_at'])
    record_audit(
        action='DISK_DELETE_COMPLETED',
        actor=user,
        target_type='disk',
        target_id=str(disk.pk),
        task_id=str(task.pk),
        details=result,
    )
    return {'disk_id': disk.pk, 'deleted': True}
