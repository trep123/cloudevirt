"""Owner-only persistent browser workspaces and single-use login bootstrap."""

import secrets
import string
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import login
from django.contrib.sessions.models import Session
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_audit
from apps.nodes.client import AgentClient
from common.errors import AppError, ErrorCode
from common.permissions import RequiresPasswordChange

from .broadcast_access import digest
from .broadcast_views import describe, hours_from, issue_link
from .models import Broadcast, MediaSource, UserWorkspace, WorkspaceControlSession
from .services import login_hash, require_transport


def endpoint():
    return settings.WORKBENCH_AGENT_ENDPOINT


def client():
    return AgentClient(endpoint(), timeout=25)


class CanUseWorkspace(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.has_perm('console.use_workspace')


def valid(workspace):
    return (
        workspace.active
        and workspace.expires_at
        and workspace.expires_at > timezone.now()
        and workspace.owner.is_active
        and not getattr(getattr(workspace.owner, 'profile', None), 'must_change_password', False)
        and workspace.owner.has_perm('console.use_workspace')
        and secrets.compare_digest(
            workspace.owner_auth_hash, workspace.owner.get_session_auth_hash()
        )
    )


def describe_workspace(workspace):
    result = {
        key: getattr(workspace, key)
        for key in ('state', 'active', 'stop_complete', 'error', 'expires_at')
    }
    result['id'] = str(workspace.pk)
    result['updated_at'] = workspace.updated_at
    result['state_fresh'] = (
        not workspace.active or (timezone.now() - workspace.updated_at).total_seconds() < 45
    )
    result['broadcast'] = describe(workspace.broadcast) if hasattr(workspace, 'broadcast') else None
    return result


def stop_workspace(workspace):
    workspace.active = False
    workspace.stop_complete = False
    workspace.state = 'STOPPING'
    workspace.bootstrap_hash = ''
    if workspace.browser_session_key:
        Session.objects.filter(session_key=workspace.browser_session_key).delete()
        workspace.browser_session_key = ''
    WorkspaceControlSession.objects.filter(workspace=workspace).update(revoked=True)
    if hasattr(workspace, 'broadcast'):
        Broadcast.objects.filter(pk=workspace.broadcast.pk).update(
            active=False, public_token_hash='', stop_complete=False, state='STOPPING'
        )
    workspace.save()


class MyWorkspaceView(APIView):
    permission_classes = [CanUseWorkspace, RequiresPasswordChange]

    def get(self, request):
        workspace = (
            UserWorkspace.objects.filter(owner=request.user)
            .select_related('broadcast__source')
            .first()
        )
        return Response(describe_workspace(workspace) if workspace else None)

    @transaction.atomic
    def post(self, request):
        require_transport(request)
        if request.session.get('workbench_id'):
            raise AppError(ErrorCode.CONFLICT, '请在本地页面管理共享工作台')
        if not settings.WORKBENCH_ENABLED:
            raise AppError(ErrorCode.CONFLICT, '共享工作台组件尚未启用，请安装 --enable-workbench')
        from django.contrib.auth import get_user_model

        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        workspace, _ = UserWorkspace.objects.select_for_update().get_or_create(owner=request.user)
        if workspace.active:
            if not valid(workspace):
                stop_workspace(workspace)
            return Response(describe_workspace(workspace), status=202)
        if not workspace.stop_complete:
            raise AppError(ErrorCode.CONFLICT, '旧工作台尚未停止，请等待资源回收')
        if hasattr(workspace, 'broadcast') and not workspace.broadcast.stop_complete:
            raise AppError(ErrorCode.CONFLICT, '旧串流尚未停止，请等待采集进程回收')
        if UserWorkspace.objects.filter(active=True).count() >= settings.WORKBENCH_MAX_SESSIONS:
            raise AppError(ErrorCode.CONFLICT, '共享工作台数量已达到上限')
        hours = hours_from(request)
        prefix = (
            '/admin/'
            if request.user.is_superuser or request.user.groups.filter(name='Admin').exists()
            else '/app/'
        )
        initial = request.data.get('initial_path', prefix + 'vms')
        if (
            not isinstance(initial, str)
            or len(initial) > 512
            or not initial.startswith(prefix)
            or any(char in initial for char in '#?\\\r\n')
            or initial.split('/')[2] == 'workbench'
        ):
            raise AppError(ErrorCode.INVALID_ARGUMENT, '工作台初始页面无效')
        workspace.generation = uuid.uuid4()
        workspace.active = True
        workspace.stop_complete = False
        workspace.state = 'QUEUED'
        workspace.error = ''
        workspace.initial_path = initial
        workspace.expires_at = timezone.now() + timedelta(hours=hours)
        workspace.owner_auth_hash = request.user.get_session_auth_hash()
        workspace.vnc_password = ''.join(
            secrets.choice(string.ascii_letters + string.digits) for _ in range(8)
        )
        workspace.bootstrap_hash = ''
        workspace.attempts = 0
        workspace.save()
        broadcast = Broadcast.objects.filter(workspace=workspace).first()
        if broadcast is None:
            source = MediaSource.objects.create(
                name=(request.user.username + ' 共享工作台')[:64],
                stream_path='pending-' + uuid.uuid4().hex,
                is_desktop=True,
            )
            broadcast = Broadcast(
                workspace=workspace, source=source, owner=request.user, kind='page'
            )
        broadcast.publish_id = workspace.generation
        broadcast.source.stream_path = 'desktop-' + workspace.generation.hex
        broadcast.source.enabled = True
        broadcast.source.save()
        broadcast.active = True
        broadcast.stop_complete = False
        broadcast.state = 'QUEUED'
        broadcast.error = ''
        broadcast.attempts = 0
        broadcast.started_at = timezone.now()
        broadcast.live_since = None
        link = issue_link(broadcast, hours)
        broadcast.link_expires_at = workspace.expires_at
        broadcast.save()
        record_audit(
            action='WORKSPACE_STARTED',
            actor=request.user,
            target_type='workspace',
            target_id=str(workspace.pk),
        )
        return Response({**describe_workspace(workspace), 'watch_path': link}, status=202)

    @transaction.atomic
    def delete(self, request):
        require_transport(request)
        workspace = get_object_or_404(UserWorkspace.objects.select_for_update(), owner=request.user)
        stop_workspace(workspace)
        record_audit(
            action='WORKSPACE_STOP_REQUESTED',
            actor=request.user,
            target_type='workspace',
            target_id=str(workspace.pk),
        )
        return Response(describe_workspace(workspace), status=202)


class WorkspaceLinkView(APIView):
    permission_classes = [CanUseWorkspace, RequiresPasswordChange]

    @transaction.atomic
    def post(self, request):
        require_transport(request)
        workspace = get_object_or_404(UserWorkspace.objects.select_for_update(), owner=request.user)
        if not valid(workspace):
            raise AppError(ErrorCode.CONFLICT, '请先开启工作台')
        broadcast = workspace.broadcast
        link = issue_link(broadcast, hours_from(request))
        broadcast.link_expires_at = min(broadcast.link_expires_at, workspace.expires_at)
        broadcast.save()
        record_audit(
            action='WORKSPACE_LINK_ROTATED',
            actor=request.user,
            target_type='workspace',
            target_id=str(workspace.pk),
        )
        return Response({'watch_path': link})


@method_decorator(ensure_csrf_cookie, name='dispatch')
class WorkspaceBootstrapView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request, pk):
        require_transport(request)
        workspace = get_object_or_404(
            UserWorkspace.objects.select_for_update().select_related('owner'), pk=pk
        )
        token = request.headers.get('X-Workspace-Bootstrap', '')
        if (
            not valid(workspace)
            or not workspace.bootstrap_expires_at
            or workspace.bootstrap_expires_at <= timezone.now()
            or len(token) > 128
            or not workspace.bootstrap_hash
            or not secrets.compare_digest(digest(token), workspace.bootstrap_hash)
        ):
            raise AppError(ErrorCode.PERMISSION_DENIED, '工作台启动凭证无效或已使用')
        login(
            request._request, workspace.owner, backend='django.contrib.auth.backends.ModelBackend'
        )
        request.session['workbench_id'] = str(workspace.pk)
        request.session['workbench_generation'] = str(workspace.generation)
        request.session.set_expiry(workspace.expires_at)
        request.session.save()
        workspace.browser_session_key = request.session.session_key
        workspace.bootstrap_hash = ''
        workspace.save(update_fields=['browser_session_key', 'bootstrap_hash'])
        response = Response({'next_path': workspace.initial_path})
        response['Cache-Control'] = 'no-store'
        return response


class WorkspaceControlView(APIView):
    permission_classes = [CanUseWorkspace, RequiresPasswordChange]

    @transaction.atomic
    def post(self, request, pk):
        require_transport(request)
        workspace = get_object_or_404(
            UserWorkspace.objects.select_for_update().select_related('owner'),
            owner=request.user,
            pk=pk,
        )
        if not valid(workspace) or workspace.state != 'READY':
            raise AppError(ErrorCode.CONFLICT, '工作台尚未就绪')
        WorkspaceControlSession.objects.filter(
            workspace=workspace, expires_at__lte=timezone.now()
        ).delete()
        if WorkspaceControlSession.objects.filter(workspace=workspace, revoked=False).count() >= 3:
            raise AppError(ErrorCode.CONFLICT, '控制连接数达到上限')
        session = WorkspaceControlSession.objects.create(
            workspace=workspace,
            user=request.user,
            generation=workspace.generation,
            login_hash=login_hash(request),
            expires_at=timezone.now() + timedelta(seconds=30),
        )
        response = Response(
            {
                'session_id': str(session.pk),
                'path': f'/console-ws/{session.pk}',
                'password': workspace.vnc_password,
            },
            status=201,
        )
        response['Cache-Control'] = 'no-store'
        return response


def owned_control(request, pk):
    session = get_object_or_404(
        WorkspaceControlSession.objects.select_related('workspace__owner'),
        pk=pk,
        user=request.user,
        login_hash=login_hash(request),
    )
    if (
        session.workspace.owner_id != request.user.pk
        or not valid(session.workspace)
        or session.generation != session.workspace.generation
    ):
        raise AppError(ErrorCode.PERMISSION_DENIED)
    return session


class WorkspaceControlLeaseView(APIView):
    permission_classes = [CanUseWorkspace, RequiresPasswordChange]

    def post(self, request, pk):
        require_transport(request)
        session = owned_control(request, pk)
        if session.revoked or not session.claimed or session.expires_at <= timezone.now():
            raise AppError(ErrorCode.CONFLICT, '控制连接已结束')
        client().request_json(f'/api/v1/console-sessions/{pk}/lease', 'POST', {})
        session.expires_at = timezone.now() + timedelta(seconds=90)
        session.save(update_fields=['expires_at'])
        return Response({'expires_at': session.expires_at})

    def delete(self, request, pk):
        session = owned_control(request, pk)
        session.revoked = True
        session.save(update_fields=['revoked'])
        try:
            client().request_json(f'/api/v1/console-sessions/{pk}', 'DELETE', {})
        except AppError:
            pass
        return Response(status=204)
