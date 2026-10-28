"""WHEP signaling proxy: SDP only, media travels directly over ICE/DTLS."""

import base64
import hashlib
import hmac
import time
import urllib.error
import urllib.request
from datetime import timedelta
from urllib.parse import quote, unquote, urljoin, urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.roles import is_admin
from apps.audit.services import record_audit
from common.errors import AppError, ErrorCode
from common.permissions import CanViewInstance, RequiresPasswordChange
from common.scope import instances_for

from .models import MediaSession, MediaSource
from .services import login_hash, require_transport


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def media_request(url, method, sdp=None):
    headers = {'Content-Type': 'application/sdp', 'Accept': 'application/sdp'}
    request = urllib.request.Request(
        url, data=sdp.encode() if sdp is not None else None, method=method, headers=headers
    )
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=10) as response:
            body = response.read(262145)
            if len(body) > 262144:
                raise AppError(ErrorCode.OPERATION_FAILED, '媒体信令响应过大')
            return body.decode(), response.headers.get('Location', ''), response.status
    except urllib.error.HTTPError as exc:
        if method == 'DELETE' and exc.code in {404, 410}:
            return '', '', exc.code
        raise AppError(
            ErrorCode.OPERATION_FAILED,
            '媒体网关未就绪或此视频源尚未发布',
            details={'upstream_status': exc.code},
        ) from exc
    except (OSError, UnicodeError) as exc:
        raise AppError(
            ErrorCode.OPERATION_FAILED, '无法连接媒体网关，请检查配置和源发布状态'
        ) from exc


def source_url(source):
    base = urlsplit(settings.MEDIA_WHEP_BASE_URL)
    if (
        base.scheme not in {'http', 'https'}
        or not base.hostname
        or base.username
        or base.password
        or base.query
        or base.fragment
    ):
        raise AppError(ErrorCode.CONFLICT, '媒体网关地址配置无效')
    return settings.MEDIA_WHEP_BASE_URL + '/' + quote(source.stream_path, safe='') + '/whep'


def safe_resource(offer_url, location):
    target = urljoin(offer_url, location)
    origin = urlsplit(offer_url)
    parsed = urlsplit(target)
    if any(segment in {'.', '..'} for segment in unquote(parsed.path).split('/')):
        raise AppError(ErrorCode.OPERATION_FAILED, '媒体会话地址包含无效路径')
    if (
        not location
        or (parsed.scheme, parsed.netloc) != (origin.scheme, origin.netloc)
        or not parsed.path.startswith(origin.path.rstrip('/') + '/')
        or parsed.query
        or parsed.fragment
    ):
        raise AppError(ErrorCode.OPERATION_FAILED, '媒体网关返回了无效会话地址')
    return target


def ice_servers(user):
    result = [{'urls': settings.MEDIA_STUN_URLS}] if settings.MEDIA_STUN_URLS else []
    if settings.MEDIA_TURN_URLS and settings.MEDIA_TURN_SECRET:
        username = f'{int(time.time()) + 600}:{user.pk}'
        credential = base64.b64encode(
            hmac.new(settings.MEDIA_TURN_SECRET.encode(), username.encode(), hashlib.sha1).digest()
        ).decode()
        result.append(
            {'urls': settings.MEDIA_TURN_URLS, 'username': username, 'credential': credential}
        )
    return result


def close_media(session):
    if session.upstream_resource:
        media_request(session.upstream_resource, 'DELETE')
    MediaSession.objects.filter(pk=session.pk).update(closed=True)


class SourceInput(serializers.Serializer):
    name = serializers.CharField(min_length=1, max_length=64)
    stream_path = serializers.RegexField(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')


class MediaSourcesView(APIView):
    permission_classes = [CanViewInstance, RequiresPasswordChange]

    def get(self, request, pk):
        get_object_or_404(instances_for(request.user), pk=pk)
        return Response(
            {
                'results': list(
                    MediaSource.objects.filter(
                        instance_id=pk, enabled=True, is_desktop=False
                    ).values('id', 'name', 'stream_path')
                ),
                'can_manage': is_admin(request.user),
                'ice_servers': ice_servers(request.user),
            }
        )

    def post(self, request, pk):
        require_transport(request)
        instance = get_object_or_404(instances_for(request.user), pk=pk)
        if not is_admin(request.user):
            raise AppError(ErrorCode.PERMISSION_DENIED)
        serializer = SourceInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        if MediaSource.objects.filter(instance=instance, enabled=True).count() >= 8:
            raise AppError(ErrorCode.CONFLICT, '每台虚拟机最多配置 8 个媒体源')
        source = MediaSource.objects.create(instance=instance, **serializer.validated_data)
        record_audit(
            action='MEDIA_SOURCE_CREATED',
            actor=request.user,
            target_type='instance',
            target_id=str(pk),
            details={'source_id': source.pk},
        )
        return Response(
            {'id': source.pk, 'name': source.name, 'stream_path': source.stream_path}, status=201
        )


class MediaSourceDetailView(APIView):
    permission_classes = [CanViewInstance, RequiresPasswordChange]

    def delete(self, request, pk):
        source = get_object_or_404(MediaSource, pk=pk, enabled=True)
        get_object_or_404(instances_for(request.user), pk=source.instance_id)
        if not is_admin(request.user):
            raise AppError(ErrorCode.PERMISSION_DENIED)
        source.enabled = False
        source.save(update_fields=['enabled'])
        for session in MediaSession.objects.filter(source=source, closed=False):
            try:
                close_media(session)
            except AppError:
                pass
        record_audit(
            action='MEDIA_SOURCE_DISABLED',
            actor=request.user,
            target_type='instance',
            target_id=str(source.instance_id),
            details={'source_id': pk},
        )
        return Response(status=204)


class MediaCreateView(APIView):
    permission_classes = [CanViewInstance, RequiresPasswordChange]

    def post(self, request, pk):
        require_transport(request)
        source = get_object_or_404(MediaSource, pk=pk, enabled=True)
        get_object_or_404(instances_for(request.user), pk=source.instance_id)
        offer = request.data.get('sdp', '')
        if (
            not isinstance(offer, str)
            or not offer.startswith('v=0')
            or len(offer.encode()) > 262144
        ):
            raise AppError(ErrorCode.INVALID_ARGUMENT, 'SDP 无效或超过 256 KiB')
        upstream = source_url(source)
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            if (
                MediaSession.objects.filter(
                    user=request.user, closed=False, expires_at__gt=timezone.now()
                ).count()
                >= 3
            ):
                raise AppError(ErrorCode.CONFLICT, '媒体会话数达到上限')
            session = MediaSession.objects.create(
                user=request.user,
                source=source,
                login_hash=login_hash(request),
                expires_at=timezone.now() + timedelta(seconds=90),
            )
        try:
            answer, location, status = media_request(upstream, 'POST', offer)
            if status != 201 or not answer.startswith('v=0'):
                raise AppError(ErrorCode.OPERATION_FAILED, '媒体网关未返回有效 SDP 答复')
            session.upstream_resource = safe_resource(upstream, location)
            session.save(update_fields=['upstream_resource'])
            source.refresh_from_db(fields=['enabled'])
            session.refresh_from_db(fields=['closed'])
            if session.closed or not source.enabled:
                close_media(session)
                raise AppError(ErrorCode.PERMISSION_DENIED, '视频源已停用')
        except AppError:
            session.closed = True
            session.save(update_fields=['closed'])
            raise
        record_audit(
            action='MEDIA_CONNECTED',
            actor=request.user,
            target_type='instance',
            target_id=str(source.instance_id),
            details={'session_id': str(session.pk)},
        )
        response = Response({'session_id': str(session.pk), 'sdp': answer}, status=201)
        response['Cache-Control'] = 'no-store'
        return response


class MediaLeaseView(APIView):
    permission_classes = [CanViewInstance, RequiresPasswordChange]

    def owned(self, request, pk):
        session = get_object_or_404(
            MediaSession.objects.select_related('source'),
            pk=pk,
            user=request.user,
            login_hash=login_hash(request),
        )
        if (
            not session.source.enabled
            or not instances_for(request.user).filter(pk=session.source.instance_id).exists()
        ):
            try:
                close_media(session)
            finally:
                raise AppError(ErrorCode.PERMISSION_DENIED)
        return session

    def post(self, request, pk):
        require_transport(request)
        session = self.owned(request, pk)
        if session.closed or session.expires_at <= timezone.now():
            raise AppError(ErrorCode.CONFLICT, '媒体会话已结束')
        session.expires_at = timezone.now() + timedelta(seconds=90)
        session.save(update_fields=['expires_at'])
        return Response({'expires_at': session.expires_at})

    def delete(self, request, pk):
        session = self.owned(request, pk)
        close_media(session)
        record_audit(
            action='MEDIA_CLOSED',
            actor=request.user,
            target_type='instance',
            target_id=str(session.source.instance_id),
            details={'session_id': str(pk)},
        )
        return Response(status=204)
