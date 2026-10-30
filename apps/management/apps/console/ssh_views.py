from datetime import timedelta
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_audit
from apps.nodes.client import AgentClient
from common.errors import AppError, ErrorCode
from common.permissions import CanViewInstance, RequiresPasswordChange, check_permission
from common.scope import instances_for

from .models import ConsoleSession
from .services import login_hash, require_transport, ssh_agent_target


def ssh_instance(request, pk):
    instance = get_object_or_404(instances_for(request.user), pk=pk)
    check_permission(
        request.user, 'instances.ssh_instance', target_type='instance', target_id=str(pk)
    )
    if (
        instance.observed_state != 'RUNNING'
        or instance.observed_state_is_stale
        or not instance.node.is_schedulable
    ):
        raise AppError(ErrorCode.CONFLICT, '请先启动虚拟机并等待状态同步，节点需可用')
    return instance


def targets(instance):
    return (
        AgentClient(instance.node.endpoint, timeout=10)
        .get_json(f'/api/v1/domains/{quote(instance.libvirt_domain_name, safe="")}/ssh-targets')
        .get('addresses', [])
    )


class SSHCreateView(APIView):
    permission_classes = [CanViewInstance, RequiresPasswordChange]

    def get(self, request, pk):
        require_transport(request)
        response = Response({'addresses': targets(ssh_instance(request, pk)), 'port': 22})
        response['Cache-Control'] = 'no-store'
        return response

    @transaction.atomic
    def post(self, request, pk):
        require_transport(request)
        if not settings.AGENT_SHARED_TOKEN:
            raise AppError(ErrorCode.CONFLICT, '节点共享令牌尚未配置')
        instance = ssh_instance(request, pk)
        ssh_agent_target(instance)
        if not isinstance(request.data, dict) or set(request.data) != {'address'}:
            raise AppError(ErrorCode.INVALID_ARGUMENT, '仅接受虚拟机地址；SSH 凭据不得提交到此接口')
        field = serializers.IPAddressField()
        address = field.run_validation(request.data['address'])
        if address not in targets(instance):
            raise AppError(ErrorCode.PERMISSION_DENIED, '地址不属于节点确认的虚拟机 DHCP 租约')
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        if (
            ConsoleSession.objects.filter(
                user=request.user, revoked=False, expires_at__gt=timezone.now()
            ).count()
            >= settings.CONSOLE_MAX_SESSIONS
        ):
            raise AppError(ErrorCode.CONFLICT, '控制台会话数达到上限，请先关闭旧会话')
        session = ConsoleSession.objects.create(
            user=request.user,
            instance=instance,
            login_hash=login_hash(request),
            protocol='ssh',
            ssh_address=address,
            expires_at=timezone.now() + timedelta(seconds=30),
        )
        record_audit(
            action='SSH_CREATED',
            actor=request.user,
            target_type='instance',
            target_id=str(pk),
            details={'session_id': str(session.pk), 'address': address, 'port': 22},
        )
        response = Response(
            {
                'session_id': str(session.pk),
                'path': f'/console-ws/{session.pk}',
                'lease_seconds': 90,
                'address': address,
                'port': 22,
            },
            status=201,
        )
        response['Cache-Control'] = 'no-store'
        return response
