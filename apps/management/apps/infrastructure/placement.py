"""Storage-pool authorization and capacity checks for VM disk placement."""

from django.db.models import Sum

from apps.accounts.roles import is_admin
from apps.instances.models import Disk, ResourceReservation
from apps.nodes.client import AgentClient
from common.errors import AppError, ErrorCode

from .models import ManagedStoragePool

GIB = 1024**3


def select_storage_pool(user, node, name=''):
    """Resolve an explicit pool or an assigned default; preserve legacy default when unassigned."""
    rows = ManagedStoragePool.objects.filter(node=node)
    if not is_admin(user):
        rows = rows.filter(allowed_users=user)
        personal = rows.filter(default_users=user).first()
        if personal:
            if name and name != personal.name:
                raise AppError(
                    ErrorCode.PERMISSION_DENIED, '当前账号必须使用管理员指定的默认存储池'
                )
            return personal
    if name == '__legacy__':
        if not is_admin(user) and rows.exists():
            raise AppError(ErrorCode.PERMISSION_DENIED, '当前账号已分配专用存储池')
        return None
    if name:
        pool = rows.filter(name=name).first()
        if pool is None:
            raise AppError(ErrorCode.PERMISSION_DENIED, '存储池不存在或无权使用')
        return pool
    preferred = rows.filter(is_default=True).first()
    if preferred:
        return preferred
    if is_admin(user):
        return None
    choices = list(rows[:2])
    if len(choices) == 1:
        return choices[0]
    if choices:
        raise AppError(ErrorCode.CONFLICT, '请指定存储池；当前账号有多个可用存储池')
    return None


def pool_available_bytes(node, pool, listing=None):
    """Verify the Agent's active pool and subtract logical disks plus in-flight reservations."""
    if listing is None:
        listing = AgentClient(node.endpoint).get_json('/api/v1/storage-pools')
    live = next((row for row in listing.get('results', []) if row.get('name') == pool.name), None)
    if (
        not live
        or live.get('type') != 'dir'
        or not live.get('active')
        or live.get('target', {}).get('path') != pool.path
    ):
        raise AppError(ErrorCode.CONFLICT, '存储池不可用或节点目录已变化，请刷新后重试')
    logical = (
        Disk.objects.filter(instance__storage_pool=pool)
        .exclude(status='DELETED')
        .exclude(instance__reservations__status='HELD')
        .aggregate(total=Sum('size_gib'))['total']
        or 0
    ) * GIB
    held = (
        ResourceReservation.objects.filter(storage_pool=pool, status='HELD').aggregate(
            total=Sum('disk_reserved_bytes')
        )['total']
        or 0
    )
    return min(
        int(live.get('available_bytes') or 0),
        int(live.get('capacity_bytes') or 0) - logical - held,
    )
