"""Guest-visible video configuration. Never silently stop a VM or claim a desktop mode."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.roles import is_admin
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


class DisplayInput(StrictInput):
    model = serializers.ChoiceField(choices=['vga', 'virtio'])
    width = serializers.IntegerField(min_value=640, max_value=3840)
    height = serializers.IntegerField(min_value=480, max_value=2160)


class InstanceDisplayView(APIView):
    permission_classes = [CanViewInstance, RequiresPasswordChange]

    def get(self, request, pk):
        instance = get_object_or_404(instances_for(request.user), pk=pk)
        client = AgentClient(instance.node.endpoint)
        return Response(
            {
                'configured': client.domain_display(instance.libvirt_domain_name),
                'video_models': client.get_json('/api/v1/node/capabilities').get(
                    'video_models', []
                ),
                'requires_shutdown': True,
            }
        )

    @transaction.atomic
    def post(self, request, pk):
        instance = get_object_or_404(
            instances_for(request.user).select_for_update(of=('self',)), pk=pk
        )
        if not is_admin(request.user):
            raise AppError(ErrorCode.PERMISSION_DENIED, '显卡变更仅限平台管理员')
        check_permission(
            request.user, 'instances.change_instance', target_type='instance', target_id=str(pk)
        )
        data = DisplayInput(data=request.data)
        data.is_valid(raise_exception=True)
        if instance.observed_state != 'SHUTOFF' or instance.observed_state_is_stale:
            raise AppError(ErrorCode.CONFLICT, '请先正常关闭虚拟机，待节点确认已关机后再修改')
        if not instance.node.is_schedulable:
            raise AppError(ErrorCode.NODE_OFFLINE, '节点不可用')
        ensure_no_active_task(instance)
        task = enqueue(
            task_type=TaskType.INSTANCE_DISPLAY,
            resource_type='instance',
            resource_id=str(pk),
            requested_by=request.user,
            payload=dict(data.validated_data),
            max_attempts=1,
        )
        instance.current_task = task
        instance.operation_status = 'PENDING'
        instance.save(update_fields=['current_task', 'operation_status', 'updated_at'])
        record_audit(
            action='INSTANCE_DISPLAY_UPDATE',
            actor=request.user,
            target_type='instance',
            target_id=str(pk),
            task_id=str(task.pk),
            details={'requested': dict(data.validated_data), 'phase': 'submitted'},
        )
        return Response(
            {
                'task': {
                    'id': str(task.pk),
                    'status': task.status,
                    'status_url': f'/api/v1/tasks/{task.pk}',
                }
            },
            status=202,
        )


def execute_instance_display(task):
    instance = Instance.objects.select_related('node').get(pk=task.resource_id, is_deleted=False)
    try:
        if (
            not task.requested_by
            or not task.requested_by.is_active
            or not is_admin(task.requested_by)
        ):
            raise AppError(ErrorCode.PERMISSION_DENIED, '发起人的显卡变更权限已失效')
        check_permission(
            task.requested_by,
            'instances.change_instance',
            target_type='instance',
            target_id=str(instance.pk),
        )
        data = DisplayInput(data=task.payload)
        data.is_valid(raise_exception=True)
        configured = AgentClient(instance.node.endpoint).domain_display(
            instance.libvirt_domain_name, dict(data.validated_data)
        )
        if configured != dict(data.validated_data):
            raise AppError(ErrorCode.OPERATION_FAILED, '节点未确认保存目标显卡配置')
    except AppError as exc:
        instance.operation_status = 'FAILED'
        instance.last_error_code, instance.last_error_message = exc.code, exc.message
        instance.save(
            update_fields=[
                'operation_status',
                'last_error_code',
                'last_error_message',
                'updated_at',
            ]
        )
        raise
    with transaction.atomic():
        instance = Instance.objects.select_for_update().get(pk=instance.pk)
        config = dict(instance.creation_config or {})
        config['hardware'] = {
            **config.get('hardware', {}),
            'video_model': configured['model'],
            'video_width': configured['width'],
            'video_height': configured['height'],
        }
        instance.creation_config, instance.operation_status = config, 'SUCCEEDED'
        instance.last_error_code = instance.last_error_message = ''
        instance.save(
            update_fields=[
                'creation_config',
                'operation_status',
                'last_error_code',
                'last_error_message',
                'updated_at',
            ]
        )
    return {
        'configured': configured,
        'guest_mode_confirmed': False,
        'message': '显卡配置已保存；下次启动生效，桌面实际模式由客体系统决定',
    }
