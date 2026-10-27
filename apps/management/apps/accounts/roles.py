"""角色与权限矩阵定义。

角色即 Django Group，权限即 Permission（ADR-006）。本模块是角色矩阵的唯一来源；
新增业务权限时在此登记，然后执行 python manage.py sync_roles 生效。
"""

import logging

from django.contrib.auth.models import Group, Permission

logger = logging.getLogger(__name__)

ROLE_ADMIN = 'Admin'
ROLE_OPERATOR = 'Operator'
ROLE_VIEWER = 'Viewer'

# Admin 使用 __ALL__ 表示拥有全部已登记权限
ALL_PERMISSIONS = '__ALL__'

ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    ROLE_ADMIN: (ALL_PERMISSIONS,),
    ROLE_OPERATOR: (
        'nodes.view_node',
        'nodes.refresh_node',
        'images.view_image',
        'images.add_image',
        'images.delete_image',
        'networks.view_network',
        'instances.view_instance',
        'instances.add_instance',
        'templates.view_template',
        'instances.start_instance',
        'instances.shutdown_instance',
        'instances.reboot_instance',
        'instances.force_stop_instance',
        'instances.delete_instance',
        'tasks.view_task',
        'tasks.cancel_task',
        'tasks.retry_task',
        'monitoring.view_alert',
        'monitoring.view_reconciliationdiff',
        'monitoring.view_reconciliationrun',
    ),
    ROLE_VIEWER: (
        'nodes.view_node',
        'images.view_image',
        'networks.view_network',
        'instances.view_instance',
        'templates.view_template',
        'tasks.view_task',
        'monitoring.view_alert',
    ),
}


def sync_role_permissions() -> dict[str, list[str]]:
    """同步角色分组与权限绑定，可重复执行。

    未在数据库中找到的权限（对应模型尚未创建）会记入报告并返回，
    便于相关模块落地后重新同步。

    Returns:
        角色 -> 尚未生效的权限码列表。
    """
    report: dict[str, list[str]] = {}
    for role_name, codenames in ROLE_PERMISSIONS.items():
        group, _ = Group.objects.get_or_create(name=role_name)
        if ALL_PERMISSIONS in codenames:
            group.permissions.set(Permission.objects.all())
            report[role_name] = []
            continue
        permissions: list[Permission] = []
        missing: list[str] = []
        for full_name in codenames:
            app_label, _, codename = full_name.partition('.')
            permission = Permission.objects.filter(
                content_type__app_label=app_label, codename=codename
            ).first()
            if permission is None:
                missing.append(full_name)
                continue
            permissions.append(permission)
        group.permissions.set(permissions)
        report[role_name] = missing
        if missing:
            logger.warning('角色权限尚未全部生效', extra={'role': role_name})
    logger.info('角色权限同步完成', extra={'missing_by_role': report})
    return report


def user_role_names(user) -> set[str]:
    """返回用户所属角色名集合。

    Args:
        user: Django 用户对象。

    Returns:
        角色名集合。
    """
    if not user or not user.is_authenticated:
        return set()
    return set(user.groups.values_list('name', flat=True))


def is_admin(user) -> bool:
    """判断用户是否属于 Admin 角色（超级用户同样视为管理员）。"""
    if not user or not user.is_authenticated:
        return False
    return bool(user.is_superuser or ROLE_ADMIN in user_role_names(user))
