"""Shared authorization rules for interactive administration and bulk jobs."""

import hashlib
import json

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import connection
from django.db.models import F, Q
from django.utils import timezone
from rest_framework import serializers

from apps.accounts.models import UserProfile
from apps.accounts.roles import ROLE_ADMIN, ROLE_PERMISSIONS, is_admin, sync_role_permissions
from common.errors import AppError, ErrorCode

BUILTINS = {'Admin': '平台管理员', 'Operator': '操作员/学员', 'Viewer': '普通用户'}
BUSINESS_APPS = {
    'instances',
    'nodes',
    'images',
    'networks',
    'templates',
    'tasks',
    'monitoring',
    'infrastructure',
}
ADMIN_ONLY = {
    'nodes.add_node',
    'networks.manage_network',
    'monitoring.run_reconciliation',
    'infrastructure.change_consoleconfiguration',
}


def serialize_admin_changes():
    if connection.vendor == 'postgresql':
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(%s)', [1130455891])


def require_admin(user, permission='accounts.manage_user'):
    if (
        not user.is_authenticated
        or not user.is_active
        or not is_admin(user)
        or not user.has_perm(permission)
    ):
        raise AppError(ErrorCode.PERMISSION_DENIED, '需要平台管理员及对应管理权限')


def permission_map():
    return {
        f'{p.content_type.app_label}.{p.codename}': p
        for p in Permission.objects.select_related('content_type')
    }


def assignable(code):
    available = {
        permission
        for role, permissions in ROLE_PERMISSIONS.items()
        if role != 'Admin'
        for permission in permissions
    }
    return code in available and code not in ADMIN_ONLY and not code.startswith('monitoring.')


def validated_roles(values):
    if (
        not isinstance(values, list)
        or not values
        or len(values) > 20
        or any(not isinstance(v, str) for v in values)
    ):
        raise serializers.ValidationError('至少选择一个有效角色，最多 20 个')
    missing_builtins = [
        name
        for name in values
        if name in BUILTINS
        and not Group.objects.filter(name=name, permissions__isnull=False).exists()
    ]
    if missing_builtins:
        sync_role_permissions()
    groups = list(Group.objects.filter(name__in=values).select_related('definition'))
    if len(groups) != len(set(values)):
        raise serializers.ValidationError('角色不存在')
    if any(hasattr(group, 'definition') and not group.definition.enabled for group in groups):
        raise serializers.ValidationError('不能分配已禁用角色')
    return sorted(set(values))


def validate_scope(value):
    if value is None:
        return value
    from apps.nodes.models import Node

    if (
        not isinstance(value, list)
        or len(value) > 1000
        or any(type(v) is not int or v < 1 for v in value)
    ):
        raise serializers.ValidationError(
            '节点范围必须是有效节点 ID 数组，null 表示继承，空数组表示无节点'
        )
    if Node.objects.filter(pk__in=value, is_deleted=False).count() != len(set(value)):
        raise serializers.ValidationError('节点不存在或已注销')
    return sorted(set(value))


def validate_quota(value):
    limits = {
        'instances': 1000000,
        'vcpu': 1000000,
        'memory_mib': 2147483647,
        'disk_gib': 2147483647,
    }
    if not isinstance(value, dict) or set(value) - set(limits):
        raise serializers.ValidationError('配额仅支持 instances、vcpu、memory_mib、disk_gib')
    if any(type(v) is not int or v < 0 or v > limits[k] for k, v in value.items()):
        raise serializers.ValidationError('配额必须为范围内的非负整数')
    return value


def protect_administrator(user, *, active=None, roles=None):
    will_admin = user.is_superuser or (
        ROLE_ADMIN in roles if roles is not None else user.groups.filter(name=ROLE_ADMIN).exists()
    )
    will_active = user.is_active if active is None else active
    if user.is_active and is_admin(user) and not (will_admin and will_active):
        others = (
            get_user_model()
            .objects.filter(is_active=True)
            .exclude(password__startswith='!')
            .filter(Q(is_superuser=True) | Q(groups__name=ROLE_ADMIN))
            .exclude(pk=user.pk)
        )
        if not others.exists():
            raise AppError(ErrorCode.CONFLICT, '不能禁用或撤销最后一个有效平台管理员')


def invalidate_user(user):
    profile, _ = UserProfile.objects.get_or_create(
        user=user, defaults={'display_name': user.username}
    )
    UserProfile.objects.filter(pk=profile.pk).update(
        session_version=F('session_version') + 1, updated_at=timezone.now()
    )
    from apps.console.models import ConsoleSession

    # Revoke renewal immediately; the existing cleanup timer closes expired agent connections.
    ConsoleSession.objects.filter(user=user, revoked=False).update(expires_at=timezone.now())
    for attribute in ['_perm_cache', '_group_perm_cache', '_user_perm_cache']:
        user.__dict__.pop(attribute, None)


def snapshot(user):
    if user is None:
        return None
    profile = getattr(user, 'profile', None)
    data = {
        'id': user.pk,
        'email': user.email,
        'active': user.is_active,
        'roles': sorted(user.groups.values_list('name', flat=True)),
        'profile': {
            key: getattr(profile, key, None)
            for key in [
                'display_name',
                'remark',
                'node_scope',
                'quota_overrides',
                'session_version',
            ]
        },
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def limit_nodes(user, ids, codename=None):
    ids = set(ids)
    if is_admin(user):
        return ids
    profile = getattr(user, 'profile', None)
    if profile is not None and profile.node_scope is not None:
        ids &= set(profile.node_scope)
    groups = user.groups.select_related('definition').prefetch_related(
        'permissions__content_type', 'definition__nodes'
    )
    allowed = set()
    if (
        codename
        and user.user_permissions.filter(
            content_type__app_label=codename.split('.')[0], codename=codename.split('.')[1]
        ).exists()
    ):
        return ids
    for group in groups:
        if codename and not any(
            f'{p.content_type.app_label}.{p.codename}' == codename for p in group.permissions.all()
        ):
            continue
        definition = getattr(group, 'definition', None)
        if definition and not definition.enabled:
            continue
        allowed |= (
            set(definition.nodes.values_list('id', flat=True))
            if definition and definition.scope == 'nodes'
            else ids
        )
    return ids & allowed if groups.exists() else ids
