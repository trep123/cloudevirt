"""节点对象级授权。

MVP 规则：
- Admin 默认对所有节点拥有全部权限；
- 显式授权优先：为用户/用户组配置了 NodeAccess 的节点，只有命中授权才可操作；
- 无任何授权记录的节点对所有已认证用户开放（向后兼容当前行为）。
"""

import logging

from django.db.models import Q

from apps.nodes.models import NodeAccess, NodePermission

logger = logging.getLogger(__name__)


def user_can_access(user, node, permission: str) -> bool:
    """判断用户是否对节点拥有指定权限。

    全局规则：只要系统中存在任意 NodeAccess 记录，就启用授权模式——
    未被显式授权的节点对非 Admin 用户不可见。
    """
    if user.is_superuser:
        return True
    if user.groups.filter(name='Admin').exists():
        return True

    has_any_global = NodeAccess.objects.exists()
    if not has_any_global:
        return True

    qs = NodeAccess.objects.filter(
        node=node,
        permission=permission,
    ).filter(Q(user=user) | Q(group__in=user.groups.all()))
    return qs.exists()


def accessible_node_ids(user, permission: str = NodePermission.OPERATE) -> set[int]:
    """返回用户可访问的节点 ID 集合（无显式授权时返回全部）。"""
    from apps.nodes.models import Node

    if user.is_superuser or user.groups.filter(name='Admin').exists():
        return set(Node.objects.filter(is_deleted=False).values_list('id', flat=True))

    explicit = NodeAccess.objects.filter(
        permission=permission,
    ).filter(Q(user=user) | Q(group__in=user.groups.all()))
    if not NodeAccess.objects.exists():
        return set(Node.objects.filter(is_deleted=False).values_list('id', flat=True))
    return set(explicit.values_list('node_id', flat=True))
