"""Admin-only draft storage backend API; configuration validation is never a probe."""

import posixpath
from urllib.parse import urlsplit

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.administration import serialize_admin_changes
from apps.audit.services import record_audit
from common.errors import AppError, ErrorCode

from .models import StorageBackend
from .storage_contracts import CONTRACT_VERSION, DRIVERS, driver_catalog, resolve_driver
from .views import ADMIN_PERMISSIONS


class StrictInput(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError(
                {'non_field_errors': ['包含不支持的字段；凭据仅接受 credential_ref 引用']}
            )
        return super().to_internal_value(data)


class DirectoryConfig(StrictInput):
    path = serializers.CharField(max_length=4096)

    def validate_path(self, value):
        if (
            not value.startswith('/')
            or '..' in value.split('/')
            or '\\' in value
            or '\x00' in value
        ):
            raise serializers.ValidationError('需要不含路径穿越的绝对目录')
        return posixpath.normpath(value)


class RBDConfig(StrictInput):
    monitors = serializers.ListField(
        child=serializers.RegexField(r'^[A-Za-z0-9.:[\]-]{1,255}$'), min_length=1, max_length=32
    )
    pool = serializers.RegexField(r'^[A-Za-z0-9_.-]{1,128}$')
    namespace = serializers.RegexField(r'^[A-Za-z0-9_.-]{0,128}$', allow_blank=True, default='')
    user = serializers.RegexField(r'^[A-Za-z0-9_.-]{1,128}$')


class S3Config(StrictInput):
    endpoint = serializers.URLField(max_length=2048)
    bucket = serializers.RegexField(r'^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$')
    region = serializers.CharField(max_length=128, default='us-east-1')
    prefix = serializers.CharField(max_length=512, allow_blank=True, default='')
    path_style = serializers.BooleanField(default=True)

    def validate_endpoint(self, value):
        url = urlsplit(value)
        if (
            url.scheme not in {'http', 'https'}
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in {'', '/'}
        ):
            raise serializers.ValidationError(
                'Endpoint 仅支持不含凭据、路径和查询参数的 HTTP(S) 地址'
            )
        return value.rstrip('/')

    def validate_prefix(self, value):
        if value.startswith('/') or '..' in value.split('/') or '\\' in value or '\x00' in value:
            raise serializers.ValidationError('对象前缀不允许绝对路径或路径穿越')
        return value


class BackendInput(StrictInput):
    name = serializers.RegexField(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$')
    driver = serializers.ChoiceField(choices=list(DRIVERS))
    usage = serializers.ChoiceField(choices=['vm_disks', 'images', 'backups'])
    configuration = serializers.DictField()
    credential_ref = serializers.RegexField(
        r'^secret://[a-zA-Z0-9][a-zA-Z0-9_.-]{0,245}$', allow_blank=True, default=''
    )
    revision = serializers.IntegerField(min_value=1, required=False)

    def validate(self, attrs):
        if attrs['usage'] not in DRIVERS[attrs['driver']]['usages']:
            raise serializers.ValidationError(
                {'usage': '该存储类型不支持此用途；S3 不能作为运行磁盘池'}
            )
        config = {'directory': DirectoryConfig, 'ceph_rbd': RBDConfig, 's3': S3Config}[
            attrs['driver']
        ](data=attrs['configuration'])
        config.is_valid(raise_exception=True)
        attrs['configuration'] = dict(config.validated_data)
        return attrs


def describe(row):
    return {
        key: getattr(row, key)
        for key in (
            'id',
            'name',
            'driver',
            'usage',
            'configuration',
            'credential_ref',
            'revision',
            'created_at',
            'updated_at',
        )
    } | {
        'state': 'draft',
        'available': False,
        'contract_version': CONTRACT_VERSION,
        'reason': '配置已保存，驱动尚未接入；未执行连接测试或解析凭据',
    }


def audit(request, action, row):
    record_audit(
        action=action,
        actor=request.user,
        target_type='storage_backend',
        target_id=str(row.pk),
        details={
            'name': row.name,
            'driver': row.driver,
            'usage': row.usage,
            'revision': row.revision,
        },
    )


class StorageDriversView(APIView):
    permission_classes = ADMIN_PERMISSIONS

    def get(self, request):
        return Response({'contract_version': CONTRACT_VERSION, 'results': driver_catalog()})


class StorageBackendListView(APIView):
    permission_classes = ADMIN_PERMISSIONS

    def get(self, request):
        from rest_framework.pagination import PageNumberPagination

        paginator = PageNumberPagination()
        paginator.page_size = 20
        rows = paginator.paginate_queryset(StorageBackend.objects.order_by('id'), request)
        return paginator.get_paginated_response([describe(row) for row in rows])

    @transaction.atomic
    def post(self, request):
        serialize_admin_changes()
        form = BackendInput(data=request.data)
        form.is_valid(raise_exception=True)
        values = dict(form.validated_data)
        values.pop('revision', None)
        if StorageBackend.objects.filter(name=values['name']).exists():
            raise AppError(ErrorCode.CONFLICT, '存储连接配置名称已存在')
        row = StorageBackend.objects.create(**values)
        audit(request, 'STORAGE_BACKEND_CREATE', row)
        return Response(describe(row), status=201)


class StorageBackendDetailView(APIView):
    permission_classes = ADMIN_PERMISSIONS

    def get(self, request, pk):
        return Response(describe(get_object_or_404(StorageBackend, pk=pk)))

    @transaction.atomic
    def put(self, request, pk):
        row = get_object_or_404(StorageBackend.objects.select_for_update(), pk=pk)
        serialize_admin_changes()
        form = BackendInput(data=request.data)
        form.is_valid(raise_exception=True)
        values = dict(form.validated_data)
        if values.pop('revision', None) != row.revision:
            raise AppError(ErrorCode.CONFLICT, '配置已变更，请刷新后提交')
        if StorageBackend.objects.filter(name=values['name']).exclude(pk=pk).exists():
            raise AppError(ErrorCode.CONFLICT, '存储连接配置名称已存在')
        for key, value in values.items():
            setattr(row, key, value)
        row.revision += 1
        row.save()
        audit(request, 'STORAGE_BACKEND_UPDATE', row)
        return Response(describe(row))

    @transaction.atomic
    def delete(self, request, pk):
        row = get_object_or_404(StorageBackend.objects.select_for_update(), pk=pk)
        audit(request, 'STORAGE_BACKEND_DELETE', row)
        row.delete()  # Draft metadata only; never touches storage or business resources.
        return Response(status=204)


class StorageBackendProbeView(APIView):
    permission_classes = ADMIN_PERMISSIONS

    def post(self, request, pk):
        resolve_driver(get_object_or_404(StorageBackend, pk=pk))
