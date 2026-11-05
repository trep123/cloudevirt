"""PVE-style virtual machine option changes backed by node confirmation."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.administration import require_admin
from apps.accounts.roles import is_admin
from apps.audit.models import AuditAction
from apps.audit.services import record_audit
from apps.instances.actions import ensure_no_active_task
from apps.instances.hardware import StrictInput
from apps.instances.models import Instance
from apps.nodes.client import AgentClient
from apps.tasks.models import TaskType
from apps.tasks.services import enqueue
from common.errors import AppError, ErrorCode
from common.permissions import CanViewInstance, RequiresPasswordChange, check_permission
from common.scope import instances_for


class InstanceOptionsInput(StrictInput):
    autostart = serializers.BooleanField()


class InstanceOptionsView(APIView):
    """Read and update safe VM options without changing guest runtime state."""

    permission_classes = [CanViewInstance, RequiresPasswordChange]

    def get(self, request, pk):
        instance = get_object_or_404(instances_for(request.user), pk=pk)
        return Response({'autostart': instance.autostart, 'requires_shutdown': False})

    @transaction.atomic
    def post(self, request, pk):
        instance = get_object_or_404(
            instances_for(request.user).select_for_update(of=('self',)), pk=pk
        )
        if not is_admin(request.user):
            raise AppError(ErrorCode.PERMISSION_DENIED, '虚拟机选项仅限平台管理员修改')
        require_admin(request.user, 'instances.change_instance')
        check_permission(
            request.user, 'instances.change_instance', target_type='instance', target_id=str(pk)
        )
        data = InstanceOptionsInput(data=request.data)
        data.is_valid(raise_exception=True)
        enabled = data.validated_data['autostart']
        if instance.autostart == enabled:
            return Response({'task': None, 'autostart': enabled, 'idempotent': True})
        if not instance.node.is_schedulable:
            raise AppError(ErrorCode.NODE_OFFLINE, '节点不可用')
        ensure_no_active_task(instance)
        task = enqueue(
            task_type=TaskType.INSTANCE_CONFIG,
            resource_type='instance',
            resource_id=str(instance.pk),
            requested_by=request.user,
            payload={'autostart': enabled, 'domain_name': instance.libvirt_domain_name},
            max_attempts=2,
        )
        instance.current_task = task
        instance.operation_status = 'PENDING'
        instance.save(update_fields=['current_task', 'operation_status', 'updated_at'])
        record_audit(
            action=AuditAction.INSTANCE_UPDATE,
            actor=request.user,
            target_type='instance',
            target_id=str(instance.pk),
            task_id=str(task.pk),
            details={'autostart': enabled},
        )
        return Response({'task': {'id': str(task.pk), 'status': task.status}}, status=202)


def execute_instance_config(task):
    """Commit options only after the node Agent accepts the libvirt change."""
    instance = Instance.objects.select_related('node').get(pk=task.resource_id, is_deleted=False)
    try:
        if not task.requested_by or not task.requested_by.is_active or not is_admin(task.requested_by):
            raise AppError(ErrorCode.PERMISSION_DENIED, '发起人的配置权限已失效')
        require_admin(task.requested_by, 'instances.change_instance')
        check_permission(
            task.requested_by,
            'instances.change_instance',
            target_type='instance',
            target_id=str(instance.pk),
        )
        enabled = bool(task.payload['autostart'])
        result = AgentClient(instance.node.endpoint).domain_autostart(
            instance.libvirt_domain_name, enabled
        )
        if result.get('autostart') is not enabled:
            raise AppError(ErrorCode.OPERATION_FAILED, '节点未确认开机自启配置')
    except AppError as exc:
        Instance.objects.filter(pk=instance.pk).update(
            operation_status='FAILED', last_error_code=exc.code, last_error_message=exc.message
        )
        raise
    with transaction.atomic():
        instance = Instance.objects.select_for_update().get(pk=instance.pk)
        instance.autostart = enabled
        instance.operation_status = 'SUCCEEDED'
        instance.last_error_code = instance.last_error_message = ''
        instance.save(
            update_fields=['autostart', 'operation_status', 'last_error_code', 'last_error_message', 'updated_at']
        )
    return {'instance_id': instance.pk, 'autostart': enabled}
