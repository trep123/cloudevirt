"""Browser-originated WHIP publishing; capability viewers remain receive-only."""

import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_audit
from common.errors import AppError, ErrorCode
from common.permissions import RequiresPasswordChange

from .broadcast_reconcile import source_ready
from .broadcast_views import hours_from, issue_link
from .media import ice_servers, media_request, safe_resource, source_url
from .models import Broadcast, MediaSource, TabShare
from .services import login_hash, require_transport
from .workspaces import CanUseWorkspace


def stop(share):
    broadcast = share.broadcast
    broadcast.active = False
    broadcast.state = 'STOPPING'
    broadcast.public_token_hash = ''
    broadcast.save()
    try:
        if share.upstream_resource:
            media_request(share.upstream_resource, 'DELETE')
        broadcast.state = 'STOPPED'
        broadcast.stop_complete = True
        broadcast.error = ''
    except AppError:
        broadcast.error = '正在等待媒体网关释放发布连接'
    broadcast.save()


def reconcile_tab(broadcast):
    share = TabShare.objects.select_related('broadcast__owner', 'broadcast__source').get(
        broadcast=broadcast
    )
    owner = broadcast.owner
    if broadcast.active and (
        share.expires_at <= timezone.now()
        or not broadcast.link_expires_at
        or broadcast.link_expires_at <= timezone.now()
        or not owner.is_active
        or not owner.has_perm('console.use_workspace')
        or not secrets.compare_digest(share.auth_hash, owner.get_session_auth_hash())
        or getattr(getattr(owner, 'profile', None), 'must_change_password', False)
    ):
        broadcast.active = False
    if not broadcast.active:
        stop(share)
        return
    try:
        broadcast.state = 'LIVE' if source_ready(broadcast.source) else 'STARTING'
        broadcast.error = '' if broadcast.state == 'LIVE' else '等待浏览器发送画面'
    except AppError as error:
        broadcast.error = error.message[:256]
    broadcast.save()


class TabSharesView(APIView):
    permission_classes = [CanUseWorkspace, RequiresPasswordChange]

    def get(self, request):
        require_transport(request)
        return Response({'ice_servers': ice_servers(request.user)})

    def post(self, request):
        require_transport(request)
        offer = request.data.get('sdp', '')
        if (
            not isinstance(offer, str)
            or not offer.startswith('v=0')
            or len(offer.encode()) > 262144
        ):
            raise AppError(ErrorCode.INVALID_ARGUMENT, 'SDP 无效或超过 256 KiB')
        try:
            request_id = uuid.UUID(str(request.data.get('request_id', '')))
        except ValueError as error:
            raise AppError(ErrorCode.INVALID_ARGUMENT, '发布请求标识无效') from error
        hours = hours_from(request)
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            if connection.vendor == 'postgresql':
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_advisory_xact_lock(%s)', [1130455890])
            if Broadcast.objects.filter(kind='tab', active=True).count() >= getattr(
                settings, 'TAB_SHARE_MAX_PUBLISHERS', 8
            ):
                raise AppError(ErrorCode.CONFLICT, '页面共享发布数已达上限，请稍后重试')
            if TabShare.objects.filter(request_id=request_id).exists():
                raise AppError(ErrorCode.CONFLICT, '此发布请求已处理，请停止后重新共享')
            if Broadcast.objects.filter(owner=request.user, kind='tab', active=True).exists():
                raise AppError(ErrorCode.CONFLICT, '已有页面正在共享，请先停止原标签页的共享')
            source = MediaSource.objects.create(
                name=(request.user.username + ' 页面共享')[:64],
                stream_path='tab-' + uuid.uuid4().hex,
                is_desktop=True,
            )
            broadcast = Broadcast(
                owner=request.user,
                source=source,
                kind='tab',
                active=True,
                stop_complete=False,
                state='STARTING',
                started_at=timezone.now(),
            )
            link = issue_link(broadcast, hours)
            broadcast.save()
            share = TabShare.objects.create(
                broadcast=broadcast,
                request_id=request_id,
                login_hash=login_hash(request),
                auth_hash=request.user.get_session_auth_hash(),
                expires_at=timezone.now() + timedelta(seconds=90),
            )
        try:
            url = source_url(source).removesuffix('/whep') + '/whip'
            answer, location, status = media_request(url, 'POST', offer)
            if status != 201 or not answer.startswith('v=0'):
                raise AppError(ErrorCode.OPERATION_FAILED, '媒体网关未返回有效发布答复')
            resource = safe_resource(url, location)
            with transaction.atomic():
                share = (
                    TabShare.objects.select_for_update()
                    .select_related('broadcast')
                    .get(pk=share.pk)
                )
                share.upstream_resource = resource
                share.save(update_fields=['upstream_resource'])
                cancelled = not share.broadcast.active
            if cancelled:
                stop(share)
                raise AppError(ErrorCode.CONFLICT, '页面共享已取消')
        except AppError:
            # Keep the upstream resource if stopping fails, so reconciliation can retry.
            share.refresh_from_db()
            stop(share)
            raise
        record_audit(
            action='TAB_SHARE_STARTED',
            actor=request.user,
            target_type='broadcast',
            target_id=str(broadcast.pk),
        )
        response = Response(
            {
                'id': str(share.pk),
                'sdp': answer,
                'watch_path': link,
                'expires_at': broadcast.link_expires_at,
            },
            status=201,
        )
        response['Cache-Control'] = 'no-store'
        return response


class TabShareLeaseView(APIView):
    permission_classes = [CanUseWorkspace, RequiresPasswordChange]

    def owned(self, request, request_id):
        return get_object_or_404(
            TabShare.objects.select_related('broadcast__owner', 'broadcast__source'),
            request_id=request_id,
            broadcast__owner=request.user,
            login_hash=login_hash(request),
        )

    def post(self, request, request_id):
        require_transport(request)
        share = self.owned(request, request_id)
        now = timezone.now()
        if (
            not share.broadcast.active
            or share.expires_at <= now
            or share.broadcast.link_expires_at <= now
            or not secrets.compare_digest(share.auth_hash, request.user.get_session_auth_hash())
        ):
            raise AppError(ErrorCode.CONFLICT, '页面共享已结束，请重新开启')
        share.expires_at = now + timedelta(seconds=90)
        share.save(update_fields=['expires_at'])
        return Response({'expires_at': share.expires_at})

    def delete(self, request, request_id):
        require_transport(request)
        share = self.owned(request, request_id)
        stop(share)
        record_audit(
            action='TAB_SHARE_STOPPED',
            actor=request.user,
            target_type='broadcast',
            target_id=str(share.broadcast_id),
        )
        return Response(status=204)
