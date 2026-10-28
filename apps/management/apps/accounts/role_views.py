from django.contrib.auth.models import Group
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_audit
from common.errors import AppError, ErrorCode
from common.permissions import RequiresPasswordChange

from .administration import (
    BUILTINS,
    assignable,
    invalidate_user,
    permission_map,
    require_admin,
    serialize_admin_changes,
    validate_scope,
)
from .models import RoleDefinition


def describe_role(group):
    definition = getattr(group, 'definition', None)
    return {
        'id': group.pk,
        'name': group.name,
        'code': group.name,
        'display_name': BUILTINS.get(
            group.name, definition.display_name if definition else group.name
        ),
        'description': definition.description
        if definition
        else {
            'Admin': '全平台管理；系统内置，不可编辑或删除',
            'Operator': '授权节点上的本人资源操作；无账号与系统管理权',
            'Viewer': '普通用户，仅本人资源；并非严格只读角色',
        }.get(group.name, ''),
        'builtin': group.name in BUILTINS,
        'enabled': definition.enabled if definition else True,
        'scope': definition.scope if definition else 'global' if group.name == 'Admin' else 'owned',
        'node_ids': list(definition.nodes.values_list('id', flat=True)) if definition else [],
        'permissions': definition.permission_codes
        if definition
        else sorted(
            f'{p.content_type.app_label}.{p.codename}'
            for p in group.permissions.select_related('content_type')
        ),
        'user_count': group.user_set.count(),
        'revision': definition.revision if definition else 0,
    }


class RoleInput(serializers.Serializer):
    code = serializers.RegexField(r'^[a-z][a-z0-9_]{2,47}$', required=False)
    display_name = serializers.CharField(max_length=64)
    description = serializers.CharField(
        max_length=500, allow_blank=True, required=False, default=''
    )
    enabled = serializers.BooleanField(default=True)
    scope = serializers.ChoiceField(choices=['owned', 'nodes'], default='owned')
    node_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), default=list)
    permissions = serializers.ListField(child=serializers.CharField(max_length=150))
    revision = serializers.IntegerField(min_value=0, required=False)

    def validate(self, attrs):
        unknown = set(self.initial_data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError('含不允许修改的角色字段')
        nodes = validate_scope(attrs.get('node_ids', []))
        if attrs.get('scope') == 'nodes' and not nodes:
            raise serializers.ValidationError({'node_ids': '指定节点范围至少选择一个节点'})
        if attrs.get('scope') == 'owned' and nodes:
            raise serializers.ValidationError({'node_ids': '本人资源模式不接受节点列表'})
        codes = set(attrs.get('permissions', []))
        catalog = permission_map()
        invalid = [code for code in codes if code not in catalog or not assignable(code)]
        if invalid:
            raise serializers.ValidationError(
                {'permissions': ['不存在或不可分配的权限：' + ','.join(sorted(invalid))]}
            )
        dependencies = {
            'instances': 'instances.view_instance',
            'nodes': 'nodes.view_node',
            'images': 'images.view_image',
            'tasks': 'tasks.view_task',
            'templates': 'templates.view_template',
        }
        for code in codes:
            dependency = dependencies.get(code.split('.')[0])
            if dependency and dependency not in codes:
                raise serializers.ValidationError({'permissions': [f'{code} 依赖 {dependency}']})
        if 'instances.add_instance' in codes:
            missing = {'nodes.view_node', 'images.view_image', 'networks.view_network'} - codes
            if missing:
                raise serializers.ValidationError(
                    {'permissions': ['创建虚拟机还依赖 ' + ','.join(sorted(missing))]}
                )
        attrs['permissions'] = sorted(codes)
        return attrs


class RoleListView(APIView):
    permission_classes = [IsAuthenticated, RequiresPasswordChange]

    def get(self, request):
        require_admin(
            request.user,
            'accounts.manage_role'
            if request.user.has_perm('accounts.manage_role')
            else 'accounts.manage_user',
        )
        return Response(
            {
                'results': [
                    describe_role(group)
                    for group in Group.objects.select_related('definition')
                    .prefetch_related('permissions__content_type', 'definition__nodes')
                    .order_by('name')
                ]
            }
        )

    @transaction.atomic
    def post(self, request):
        require_admin(request.user, 'accounts.manage_role')
        serialize_admin_changes()
        serializer = RoleInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        code = data.get('code')
        if not code or Group.objects.filter(name__iexact=code).exists():
            raise AppError(ErrorCode.CONFLICT, '角色编码缺失或已存在')
        group = Group.objects.create(name=code)
        definition = RoleDefinition.objects.create(
            group=group,
            display_name=data['display_name'],
            description=data['description'],
            enabled=data['enabled'],
            scope=data['scope'],
            permission_codes=data['permissions'],
        )
        definition.nodes.set(data['node_ids'])
        if definition.enabled:
            catalog = permission_map()
            group.permissions.set([catalog[code] for code in data['permissions']])
        record_audit(
            action='ROLE_CREATE',
            actor=request.user,
            target_type='role',
            target_id=str(group.pk),
            details=describe_role(group),
        )
        return Response(describe_role(group), status=201)


class RoleDetailView(APIView):
    permission_classes = [IsAuthenticated, RequiresPasswordChange]

    def owned(self, request, pk):
        require_admin(request.user, 'accounts.manage_role')
        group = get_object_or_404(Group.objects.select_for_update(), pk=pk)
        if group.name in BUILTINS:
            raise AppError(ErrorCode.CONFLICT, '内置角色不可编辑或删除，请创建自定义角色')
        return group

    @transaction.atomic
    def patch(self, request, pk):
        serialize_admin_changes()
        group = self.owned(request, pk)
        before = describe_role(group)
        serializer = RoleInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if 'code' in data and data['code'] != group.name:
            raise AppError(ErrorCode.CONFLICT, '角色编码不可修改')
        definition = getattr(group, 'definition', None)
        if data.get('revision') != (definition.revision if definition else 0):
            raise AppError(ErrorCode.CONFLICT, '角色已变更，请刷新后编辑')
        if definition is None:
            definition = RoleDefinition(group=group)
        for key in ['display_name', 'description', 'enabled', 'scope']:
            setattr(definition, key, data[key])
        definition.permission_codes = data['permissions']
        definition.revision += 1
        definition.save()
        definition.nodes.set(data['node_ids'])
        catalog = permission_map()
        group.permissions.set(
            [catalog[code] for code in data['permissions']] if data['enabled'] else []
        )
        for user in group.user_set.all():
            invalidate_user(user)
        record_audit(
            action='ROLE_UPDATE',
            actor=request.user,
            target_type='role',
            target_id=str(pk),
            details={'before': before, 'after': describe_role(group)},
        )
        return Response(describe_role(group))

    @transaction.atomic
    def delete(self, request, pk):
        serialize_admin_changes()
        group = self.owned(request, pk)
        if group.user_set.exists():
            raise AppError(ErrorCode.CONFLICT, '角色仍关联用户，请先迁移用户角色')
        before = describe_role(group)
        group.delete()
        record_audit(
            action='ROLE_DELETE',
            actor=request.user,
            target_type='role',
            target_id=str(pk),
            details=before,
        )
        return Response(status=204)


class PermissionCatalogView(APIView):
    permission_classes = [IsAuthenticated, RequiresPasswordChange]

    def get(self, request):
        require_admin(request.user, 'accounts.manage_role')
        return Response(
            {
                'results': [
                    {
                        'code': code,
                        'name': permission.name,
                        'module': permission.content_type.app_label,
                        'assignable': assignable(code),
                    }
                    for code, permission in sorted(permission_map().items())
                ]
            }
        )
