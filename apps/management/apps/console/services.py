"""Opaque browser IDs, server-only node routing and one-use tickets."""

import base64
import hashlib
import hmac
import json
import socket
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.audit.services import record_audit
from apps.nodes.client import AgentClient
from common.errors import AppError, ErrorCode

from .models import ConsoleSession


def login_hash(request):
    key = request.session.session_key
    if not key:
        raise AppError(ErrorCode.UNAUTHORIZED)
    return hashlib.sha256(key.encode()).hexdigest()


def require_transport(request):
    if settings.CONSOLE_REQUIRE_TLS and not request.is_secure():
        raise AppError(ErrorCode.PERMISSION_DENIED, '控制台需要 HTTPS')


def origin_matches(request):
    origin = urlsplit(request.headers.get('Origin', ''))
    expected = urlsplit(request.build_absolute_uri('/'))
    return (
        origin.scheme == expected.scheme
        and origin.netloc == expected.netloc
        and origin.scheme in {'http', 'https'}
    )


def agent_target(instance):
    endpoint = urlsplit(instance.node.endpoint)
    if (
        endpoint.scheme not in {'http', 'https'}
        or not endpoint.hostname
        or endpoint.username
        or endpoint.password
        or endpoint.query
        or endpoint.fragment
        or endpoint.path not in {'', '/'}
    ):
        raise AppError(ErrorCode.CONFLICT, '节点 Agent 地址配置无效')
    port = endpoint.port or (443 if endpoint.scheme == 'https' else 80)
    try:
        address = socket.getaddrinfo(endpoint.hostname, port, type=socket.SOCK_STREAM)[0][4][0]
    except OSError as exc:
        raise AppError(ErrorCode.NODE_OFFLINE, '节点地址无法解析') from exc
    host = f'[{address}]' if ':' in address else address
    return f'{endpoint.scheme}://{host}:{port}/vnc', endpoint.hostname


@transaction.atomic
def create_desktop(request, instance):
    require_transport(request)
    if not settings.AGENT_SHARED_TOKEN:
        raise AppError(ErrorCode.CONFLICT, '节点共享令牌尚未配置')
    get_user_model().objects.select_for_update().get(pk=request.user.pk)
    if instance.observed_state != 'RUNNING' or not instance.node.is_schedulable:
        raise AppError(ErrorCode.CONFLICT, '虚拟机必须运行且节点可用')
    if not instance.vnc_password:
        raise AppError(ErrorCode.CONFLICT, '实例未启用图形控制台')
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
        expires_at=timezone.now() + timedelta(seconds=30),
    )
    record_audit(
        action='CONSOLE_CREATED',
        actor=request.user,
        target_type='instance',
        target_id=str(instance.pk),
        details={'session_id': str(session.pk)},
    )
    return {
        'type': 'vnc',
        'session_id': str(session.pk),
        'path': f'/console-ws/{session.pk}',
        'password': instance.vnc_password,
        'expires_at': int(session.expires_at.timestamp()),
        'lease_seconds': 90,
    }


def ticket(session):
    payload = {
        'sid': str(session.pk),
        'domain': session.instance.libvirt_domain_name,
        'exp': int(timezone.now().timestamp()) + 30,
    }
    encoded = (
        base64.urlsafe_b64encode(json.dumps(payload, separators=(',', ':')).encode())
        .decode()
        .rstrip('=')
    )
    signature = hmac.new(
        settings.AGENT_SHARED_TOKEN.encode(), ('console-v1.' + encoded).encode(), hashlib.sha256
    ).hexdigest()
    return encoded + '.' + signature


def gateway_key():
    return hmac.new(settings.SECRET_KEY.encode(), b'console-gateway-v1', hashlib.sha256).hexdigest()


def close_desktop(session):
    ConsoleSession.objects.filter(pk=session.pk).update(revoked=True)
    try:
        AgentClient(session.instance.node.endpoint, timeout=3).request_json(
            f'/api/v1/console-sessions/{session.pk}', 'DELETE'
        )
    except AppError:
        pass
