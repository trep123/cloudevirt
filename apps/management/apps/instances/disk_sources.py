"""Administrator-only retained system disk sources; never accept client paths."""

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.administration import require_admin
from apps.instances.models import Disk
from apps.tasks.models import TERMINAL_STATUSES, Task
from common.errors import AppError, ErrorCode
from common.permissions import CanCreateInstance, RequiresPasswordChange


def sources():
    return (
        Disk.objects.select_related('instance', 'instance__node', 'instance__image')
        .filter(
            role='SYSTEM',
            format__iexact='qcow2',
            is_orphan=True,
        )
        .filter(status__in=['READY', 'DETACHED'])
        .filter(Q(instance__is_deleted=True) | Q(status='DETACHED'))
    )


def source_disk(user, pk, node_id=None, lock=False):
    require_admin(user, 'instances.add_instance')
    query = sources()
    if lock:
        query = query.select_for_update(of=('self',))
    disk = get_object_or_404(query, pk=pk)
    if node_id is not None and disk.instance.node_id != node_id:
        raise AppError(ErrorCode.CONFLICT, '系统盘位于其他节点')
    if (
        Task.objects.filter(resource_type='instance', resource_id=str(disk.instance_id))
        .exclude(status__in=TERMINAL_STATUSES)
        .exists()
    ):
        raise AppError(ErrorCode.CONFLICT, '源磁盘所属实例存在未完成任务')
    return disk


def cloning(disk_id):
    return (
        Task.objects.filter(
            type='INSTANCE_CREATE', payload__creation_config__source_disk__id=disk_id
        )
        .exclude(status__in=TERMINAL_STATUSES)
        .exists()
    )


def inspect_file(user, node, path, check_registered=True, storage_pool=''):
    from pathlib import PurePosixPath

    from apps.accounts.administration import limit_nodes
    from apps.nodes.access import user_can_access
    from apps.nodes.client import AgentClient
    from apps.nodes.models import NodePermission

    require_admin(user, 'instances.add_instance')
    if (
        not isinstance(path, str)
        or not path
        or len(path) > 255
        or len(PurePosixPath(path).name) > 128
        or path.startswith('/')
        or '\\' in path
        or any(part.startswith('.') for part in PurePosixPath(path).parts)
        or str(PurePosixPath(path)) != path
    ):
        raise AppError(ErrorCode.INVALID_ARGUMENT, '请使用节点磁盘目录内的规范相对路径')
    if node.pk not in limit_nodes(user, [node.pk], 'instances.add_instance') or not user_can_access(
        user, node, NodePermission.OPERATE
    ):
        raise AppError(ErrorCode.PERMISSION_DENIED)
    from apps.infrastructure.placement import select_storage_pool

    pool = select_storage_pool(user, node, storage_pool)
    if (
        check_registered
        and Disk.objects.filter(
            relative_path=path, instance__node=node, instance__storage_pool=pool
        )
        .exclude(status='DELETED')
        .exists()
    ):
        raise AppError(ErrorCode.CONFLICT, '文件已登记为数据卷，不能重复直接挂载')
    info = AgentClient(node.endpoint).request_json(
        '/api/v1/disks/inspect',
        'POST',
        {
            'relative_path': path,
            **({'storage_pool': pool.name} if pool else {}),
        },
    )
    if (
        info.get('format') != 'QCOW2'
        or not isinstance(info.get('virtual_size_bytes'), int)
        or info['virtual_size_bytes'] <= 0
    ):
        raise AppError(ErrorCode.CONFLICT, '节点未返回有效的独立 QCOW2 系统盘')
    return info


class SystemDiskSourcesView(APIView):
    permission_classes = [CanCreateInstance, RequiresPasswordChange]

    def get(self, request):
        from apps.accounts.administration import limit_nodes
        from apps.nodes.client import AgentClient
        from apps.nodes.models import Node

        require_admin(request.user, 'instances.add_instance')
        if not request.query_params.get('node'):
            return Response({'results': [], 'directory': ''})
        from rest_framework import serializers

        node_id = serializers.IntegerField(min_value=1).run_validation(request.query_params['node'])
        node = get_object_or_404(Node, pk=node_id, is_deleted=False)
        if node.pk not in limit_nodes(request.user, [node.pk], 'instances.add_instance'):
            raise AppError(ErrorCode.PERMISSION_DENIED)
        path = request.query_params.get('path')
        from urllib.parse import urlencode

        from apps.infrastructure.placement import select_storage_pool

        pool_name = request.query_params.get('storage_pool', '')
        pool = select_storage_pool(request.user, node, pool_name)
        if path:
            return Response(inspect_file(request.user, node, path, storage_pool=pool_name))
        query = '?' + urlencode({'storage_pool': pool.name}) if pool else ''
        listing = AgentClient(node.endpoint).get_json('/api/v1/disks' + query)
        registered = set(
            Disk.objects.filter(instance__node=node, instance__storage_pool=pool)
            .exclude(status='DELETED')
            .values_list('relative_path', flat=True)
        )
        return Response(
            {
                'directory': listing.get('directory', ''),
                'results': [
                    d
                    for d in listing.get('disks', [])
                    if d.get('format') == 'QCOW2' and d.get('name') not in registered
                ],
            }
        )
