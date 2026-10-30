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


class SystemDiskSourcesView(APIView):
    permission_classes = [CanCreateInstance, RequiresPasswordChange]

    def get(self, request):
        require_admin(request.user, 'instances.add_instance')
        query = sources().filter(instance__node__is_deleted=False)
        return Response(
            {
                'results': [
                    {
                        'id': d.pk,
                        'name': d.name,
                        'instance_name': d.instance.name,
                        'node': d.instance.node_id,
                        'node_name': d.instance.node.name,
                        'size_gib': d.size_gib,
                        'image': d.instance.image_id,
                    }
                    for d in query.order_by('-pk')[:200]
                ]
            }
        )
