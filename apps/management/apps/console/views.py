import re
import secrets
import uuid
from datetime import timedelta

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_audit
from apps.nodes.client import AgentClient
from common.errors import AppError, ErrorCode
from common.permissions import CanViewInstance, RequiresPasswordChange, check_permission
from common.scope import instances_for

from .models import ConsoleSession
from .services import (
    agent_target,
    close_desktop,
    create_desktop,
    gateway_key,
    login_hash,
    origin_matches,
    require_transport,
    ssh_agent_target,
    ticket,
)


class DesktopCreateView(APIView):
    permission_classes = [CanViewInstance, RequiresPasswordChange]

    def post(self, request, pk):
        instance = get_object_or_404(instances_for(request.user), pk=pk)
        response = Response(create_desktop(request, instance), status=201)
        response['Cache-Control'] = 'no-store'
        return response


def owned_desktop(request, pk, lock=False):
    query = ConsoleSession.objects.select_related('instance__node')
    if lock:
        query = query.select_for_update()
    session = get_object_or_404(query, pk=pk, user=request.user, login_hash=login_hash(request))
    if not instances_for(request.user).filter(pk=session.instance_id).exists():
        close_desktop(session)
        raise AppError(ErrorCode.PERMISSION_DENIED)
    check_permission(
        request.user,
        'instances.view_instance',
        target_type='instance',
        target_id=str(session.instance_id),
    )
    if session.protocol == 'ssh':
        check_permission(
            request.user,
            'instances.ssh_instance',
            target_type='instance',
            target_id=str(session.instance_id),
        )
    return session


class DesktopAuthorizeView(APIView):
    permission_classes = [CanViewInstance, RequiresPasswordChange]

    @transaction.atomic
    def get(self, request):
        if not secrets.compare_digest(
            request.headers.get('X-Console-Gateway-Key', ''), gateway_key()
        ):
            raise AppError(ErrorCode.PERMISSION_DENIED)
        require_transport(request)
        if not origin_matches(request):
            raise AppError(ErrorCode.PERMISSION_DENIED, 'WebSocket 来源不匹配')
        match = re.fullmatch(
            r'/console-ws/([0-9a-f-]{36})', request.headers.get('X-Original-URI', '')
        )
        if not match:
            raise AppError(ErrorCode.PERMISSION_DENIED)
        try:
            uuid.UUID(match[1])
        except ValueError as exc:
            raise AppError(ErrorCode.PERMISSION_DENIED) from exc
        session = owned_desktop(request, match[1], lock=True)
        if session.claimed or session.revoked or session.expires_at <= timezone.now():
            raise AppError(ErrorCode.PERMISSION_DENIED, '控制台票据已使用或过期，请重新授权')
        if session.protocol == 'ssh':
            target, host = ssh_agent_target(session.instance)
        else:
            target, host = agent_target(session.instance)
        session.claimed = True
        session.expires_at = timezone.now() + timedelta(seconds=90)
        session.save(update_fields=['claimed', 'expires_at'])
        response = Response(status=204)
        response['X-Console-Target'] = target
        response['X-Console-Node-Host'] = host
        response['X-Console-Ticket'] = ticket(session)
        response['Cache-Control'] = 'no-store'
        record_audit(
            action='CONSOLE_CONNECTED',
            actor=request.user,
            target_type='instance',
            target_id=str(session.instance_id),
            details={'session_id': str(session.pk)},
        )
        return response


class CanUseDesktopSession(CanViewInstance):
    # URL pk is a ConsoleSession UUID. Instance scope is checked after resolving
    # ownership in owned_desktop(), never by treating this UUID as Instance.pk.
    target_type = 'console_session'


class DesktopLeaseView(APIView):
    permission_classes = [CanUseDesktopSession, RequiresPasswordChange]

    @transaction.atomic
    def post(self, request, pk):
        require_transport(request)
        session = owned_desktop(request, pk, lock=True)
        if session.revoked or not session.claimed or session.expires_at <= timezone.now():
            raise AppError(ErrorCode.CONFLICT, '会话已结束，请重新连接')
        AgentClient(session.instance.node.endpoint, timeout=5).request_json(
            f'/api/v1/console-sessions/{session.pk}/lease', 'POST', {}
        )
        session.expires_at = timezone.now() + timedelta(seconds=90)
        session.save(update_fields=['expires_at'])
        return Response({'expires_at': session.expires_at})

    @transaction.atomic
    def delete(self, request, pk):
        session = owned_desktop(request, pk, lock=True)
        close_desktop(session)
        record_audit(
            action='CONSOLE_CLOSED',
            actor=request.user,
            target_type='instance',
            target_id=str(session.instance_id),
            details={'session_id': str(session.pk)},
        )
        return Response(status=204)
