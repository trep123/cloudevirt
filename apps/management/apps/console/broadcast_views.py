"""Asynchronous publishing control and anonymous, scoped WHEP viewing."""

import secrets
import uuid
from datetime import timedelta
from types import SimpleNamespace

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_audit
from common.errors import AppError, ErrorCode
from common.permissions import CanViewInstance, RequiresPasswordChange
from common.scope import instances_for

from .broadcast_access import digest, policy_for
from .media import close_media, ice_servers, media_request, safe_resource, source_url
from .models import Broadcast, MediaSession, MediaSource
from .services import origin_matches, require_transport


def describe(broadcast):
    return {
        'id': str(broadcast.pk),
        'kind': broadcast.kind,
        'name': broadcast.source.name,
        'source_id': broadcast.source_id,
        'active': broadcast.active,
        'state': broadcast.state,
        'state_fresh': not broadcast.active
        or (timezone.now() - broadcast.updated_at).total_seconds() < 45,
        'stop_complete': broadcast.stop_complete,
        'error': broadcast.error,
        'link_expires_at': broadcast.link_expires_at,
        'updated_at': broadcast.updated_at,
    }


def issue_link(broadcast, hours):
    token = secrets.token_urlsafe(32)
    broadcast.public_token_hash = digest(token)
    broadcast.access_version = uuid.uuid4()
    broadcast.link_expires_at = timezone.now() + timedelta(hours=hours)
    return '/watch#' + str(broadcast.pk) + '.' + token


def hours_from(request):
    hours = request.data.get('expires_hours', 12)
    if type(hours) is not int or not 1 <= hours <= 24:
        raise AppError(ErrorCode.INVALID_ARGUMENT, '观看链接有效期必须为 1–24 小时')
    return hours


class BroadcastsView(APIView):
    permission_classes = [CanViewInstance, RequiresPasswordChange]

    def get(self, request, pk):
        instance = get_object_or_404(instances_for(request.user), pk=pk)
        return Response(
            {
                'results': [
                    describe(item)
                    for item in Broadcast.objects.filter(instance=instance).select_related('source')
                ]
            }
        )

    @transaction.atomic
    def post(self, request, pk):
        require_transport(request)
        instance = get_object_or_404(instances_for(request.user).select_for_update(), pk=pk)
        kind = request.data.get('kind')
        hours = hours_from(request)
        if kind == 'desktop':
            if (
                instance.observed_state != 'RUNNING'
                or not instance.node.is_schedulable
                or not instance.vnc_password
            ):
                raise AppError(ErrorCode.CONFLICT, '桌面串流要求虚拟机运行、节点可用且已启用 VNC')
            broadcast = (
                Broadcast.objects.filter(instance=instance, kind='desktop')
                .select_related('source')
                .first()
            )
            if broadcast is None:
                source = MediaSource.objects.create(
                    instance=instance,
                    name=(instance.name + ' 桌面')[:64],
                    stream_path='pending-' + uuid.uuid4().hex,
                    is_desktop=True,
                )
                broadcast = Broadcast.objects.create(
                    instance=instance, source=source, owner=request.user, kind=kind
                )
        elif kind == 'source':
            source = get_object_or_404(
                MediaSource,
                pk=request.data.get('source_id'),
                instance=instance,
                enabled=True,
                is_desktop=False,
            )
            broadcast, _ = Broadcast.objects.get_or_create(
                source=source, defaults={'instance': instance, 'owner': request.user, 'kind': kind}
            )
        else:
            raise AppError(ErrorCode.INVALID_ARGUMENT, '串流类型无效')
        if broadcast.active:
            return Response(describe(broadcast), status=202)
        if not broadcast.stop_complete:
            raise AppError(ErrorCode.CONFLICT, '旧串流尚未停止，请等待完成后重开')
        # Serialize the user's admission separately from the per-resource lock.
        from django.contrib.auth import get_user_model

        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        if Broadcast.objects.filter(owner=request.user, active=True).count() >= 3:
            raise AppError(ErrorCode.CONFLICT, '最多同时开启 3 路串流')
        broadcast.owner = request.user
        broadcast.publish_id = uuid.uuid4()
        if kind == 'desktop':
            broadcast.source.stream_path = 'desktop-' + broadcast.publish_id.hex
            broadcast.source.enabled = True
            broadcast.source.save(update_fields=['stream_path', 'enabled'])
        broadcast.active = True
        broadcast.stop_complete = False
        broadcast.state = 'QUEUED'
        broadcast.error = ''
        broadcast.attempts = 0
        broadcast.started_at = timezone.now()
        broadcast.live_since = None
        link = issue_link(broadcast, hours)
        broadcast.save()
        record_audit(
            action='BROADCAST_OPENED',
            actor=request.user,
            target_type='broadcast',
            target_id=str(broadcast.pk),
            details={'kind': kind},
        )
        return Response({**describe(broadcast), 'watch_path': link}, status=202)


class BroadcastControlView(APIView):
    permission_classes = [CanViewInstance, RequiresPasswordChange]

    def owned(self, request, pk):
        broadcast = get_object_or_404(
            Broadcast.objects.select_for_update().select_related('source'),
            pk=pk,
            instance__in=instances_for(request.user),
        )
        return broadcast

    @transaction.atomic
    def post(self, request, pk):
        require_transport(request)
        broadcast = self.owned(request, pk)
        if not broadcast.active:
            raise AppError(ErrorCode.CONFLICT, '请先开启串流')
        link = issue_link(broadcast, hours_from(request))
        broadcast.save()
        record_audit(
            action='BROADCAST_LINK_ROTATED',
            actor=request.user,
            target_type='broadcast',
            target_id=str(pk),
        )
        return Response({**describe(broadcast), 'watch_path': link})

    @transaction.atomic
    def delete(self, request, pk):
        require_transport(request)
        broadcast = self.owned(request, pk)
        broadcast.active = False
        broadcast.stop_complete = False
        broadcast.state = 'STOPPING'
        broadcast.public_token_hash = ''
        broadcast.access_version = uuid.uuid4()
        broadcast.save()
        record_audit(
            action='BROADCAST_STOP_REQUESTED',
            actor=request.user,
            target_type='broadcast',
            target_id=str(pk),
        )
        return Response(describe(broadcast), status=202)


def public_broadcast(request, pk, lock=False):
    require_transport(request)
    if request.headers.get('Origin') and not origin_matches(request):
        raise AppError(ErrorCode.PERMISSION_DENIED, '观看请求来源不匹配')
    query = Broadcast.objects.select_related('source', 'owner')
    if lock:
        query = query.select_for_update()
    broadcast = get_object_or_404(query, pk=pk)
    policy_for(broadcast).authorize(request, broadcast)
    return broadcast


class PublicBroadcastView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, pk):
        broadcast = public_broadcast(request, pk)
        response = Response(
            {
                'id': str(broadcast.pk),
                'name': broadcast.source.name,
                'state': broadcast.state,
                'can_connect': broadcast.kind == 'source' or broadcast.state == 'LIVE',
                'expires_at': broadcast.link_expires_at,
                'ice_servers': ice_servers(SimpleNamespace(pk='stream-' + broadcast.pk.hex)),
            }
        )
        response['Cache-Control'] = 'no-store'
        return response

    def post(self, request, pk):
        offer = request.data.get('sdp', '')
        if (
            not isinstance(offer, str)
            or not offer.startswith('v=0')
            or len(offer.encode()) > 262144
        ):
            raise AppError(ErrorCode.INVALID_ARGUMENT, 'SDP 无效或超过 256 KiB')
        lease_token = secrets.token_urlsafe(32)
        with transaction.atomic():
            broadcast = public_broadcast(request, pk, lock=True)
            if broadcast.state != 'LIVE' and broadcast.kind != 'source':
                raise AppError(ErrorCode.CONFLICT, '串流尚未就绪，请等待发布端状态更新')
            if MediaSession.objects.filter(
                broadcast=broadcast, closed=False, expires_at__gt=timezone.now()
            ).count() >= getattr(settings, 'BROADCAST_MAX_VIEWERS', 16):
                raise AppError(ErrorCode.RATE_LIMITED, '此串流观看会话已达上限')
            session = MediaSession.objects.create(
                source=broadcast.source,
                broadcast=broadcast,
                access_version=broadcast.access_version,
                viewer_token_hash=digest(lease_token),
                expires_at=timezone.now() + timedelta(seconds=90),
                login_hash='',
            )
        try:
            answer, location, status = media_request(source_url(broadcast.source), 'POST', offer)
            if status != 201 or not answer.startswith('v=0'):
                raise AppError(ErrorCode.OPERATION_FAILED, '媒体网关未返回有效答复')
            session.upstream_resource = safe_resource(source_url(broadcast.source), location)
            session.save(update_fields=['upstream_resource'])
            broadcast.refresh_from_db()
            if not policy_for(broadcast).session_valid(session):
                close_media(session)
                raise AppError(ErrorCode.PERMISSION_DENIED, '观看授权已撤销')
        except AppError:
            session.closed = True
            session.save(update_fields=['closed'])
            raise
        record_audit(
            action='BROADCAST_WATCH_OPENED',
            target_type='broadcast',
            target_id=str(pk),
            details={'session_id': str(session.pk)},
        )
        response = Response(
            {'session_id': str(session.pk), 'sdp': answer, 'lease_token': lease_token}, status=201
        )
        response['Cache-Control'] = 'no-store'
        return response


class PublicWatchLeaseView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def owned(self, request, pk):
        require_transport(request)
        session = get_object_or_404(
            MediaSession.objects.select_related('broadcast__owner'),
            pk=pk,
            broadcast__isnull=False,
            user__isnull=True,
        )
        token = request.headers.get('X-Media-Session-Token', '')
        if len(token) > 128 or not secrets.compare_digest(digest(token), session.viewer_token_hash):
            raise AppError(ErrorCode.PERMISSION_DENIED)
        return session

    def post(self, request, pk):
        session = self.owned(request, pk)
        if (
            session.closed
            or session.expires_at <= timezone.now()
            or not policy_for(session.broadcast).session_valid(session)
        ):
            close_media(session)
            raise AppError(ErrorCode.PERMISSION_DENIED, '观看会话已结束')
        session.expires_at = min(
            timezone.now() + timedelta(seconds=90), session.broadcast.link_expires_at
        )
        session.save(update_fields=['expires_at'])
        return Response({'expires_at': session.expires_at})

    def delete(self, request, pk):
        close_media(self.owned(request, pk))
        return Response(status=204)
