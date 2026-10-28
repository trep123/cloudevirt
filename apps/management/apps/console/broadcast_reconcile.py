"""Server-owned publishing lifecycle. The owner's browser is never the producer."""

import json
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, urlsplit

from django.conf import settings
from django.db import close_old_connections, transaction
from django.db.models import Q
from django.utils import timezone

from apps.nodes.client import AgentClient
from common.errors import AppError, ErrorCode
from common.scope import instances_for

from .media import NoRedirect
from .models import Broadcast


def source_ready(source):
    base = getattr(settings, 'MEDIA_API_BASE_URL', 'http://127.0.0.1:9997').rstrip('/')
    parsed = urlsplit(base)
    if (
        parsed.scheme not in {'http', 'https'}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise AppError(ErrorCode.CONFLICT, '媒体管理地址配置无效')
    try:
        with urllib.request.build_opener(NoRedirect()).open(
            base + '/v3/paths/get/' + quote(source.stream_path, safe=''), timeout=3
        ) as response:
            body = response.read(65537)
            if len(body) > 65536:
                raise ValueError()
            return json.loads(body).get('ready') is True
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return False
        raise AppError(ErrorCode.OPERATION_FAILED, '无法查询媒体网关') from error
    except (OSError, ValueError) as error:
        raise AppError(ErrorCode.OPERATION_FAILED, '无法查询媒体网关') from error


def reconcile_one(pk, reset_connections=True):
    if reset_connections:
        close_old_connections()
    try:
        with transaction.atomic():
            broadcast = (
                Broadcast.objects.select_for_update(of=('self',), skip_locked=True)
                .select_related('source', 'instance__node', 'owner', 'workspace__owner')
                .filter(pk=pk)
                .first()
            )
            if broadcast is None:
                return
            now = timezone.now()
            owner = broadcast.owner
            allowed = (
                owner.is_active
                and owner.has_perm('instances.view_instance')
                and instances_for(owner).filter(pk=broadcast.instance_id).exists()
            )
            if broadcast.kind == 'page':
                from .workspaces import valid

                allowed = valid(broadcast.workspace)
            if broadcast.active and (
                not allowed
                or not broadcast.source.enabled
                or not broadcast.link_expires_at
                or broadcast.link_expires_at <= now
            ):
                broadcast.active = False
                broadcast.stop_complete = False
                broadcast.state = 'STOPPING'
                broadcast.public_token_hash = ''
            endpoint = (
                settings.WORKBENCH_AGENT_ENDPOINT
                if broadcast.kind == 'page'
                else broadcast.instance.node.endpoint
            )
            client = AgentClient(endpoint, timeout=3)
            path = '/api/v1/desktop-streams/' + str(broadcast.publish_id)
            if not broadcast.active:
                try:
                    if broadcast.kind in {'desktop', 'page'}:
                        result = client.request_json(path, 'DELETE', {})
                        if result.get('status') != 'STOPPED':
                            broadcast.save()
                            return
                    broadcast.stop_complete = True
                    if broadcast.state != 'ERROR':
                        broadcast.state = 'STOPPED'
                except AppError:
                    broadcast.error = '正在等待节点停止采集；未续租的进程会自动退出'
                broadcast.save()
                return
            try:
                if broadcast.kind == 'page':
                    if broadcast.workspace.state != 'READY':
                        broadcast.state = 'STARTING'
                        broadcast.error = '正在建立服务端工作台'
                        broadcast.save()
                        return
                    client.request_json(
                        path,
                        'POST',
                        {
                            'workspace': str(broadcast.workspace_id),
                            'generation': str(broadcast.publish_id),
                            'password': broadcast.workspace.vnc_password,
                        },
                    )
                if broadcast.kind == 'desktop':
                    if broadcast.instance.observed_state != 'RUNNING':
                        raise AppError(ErrorCode.CONFLICT, '虚拟机已不在运行状态')
                    client.request_json(
                        path,
                        'POST',
                        {
                            'domain': broadcast.instance.libvirt_domain_name,
                            'password': broadcast.instance.vnc_password,
                        },
                    )
                ready = source_ready(broadcast.source)
                if ready:
                    broadcast.state = 'LIVE'
                    broadcast.error = ''
                    if broadcast.live_since is None:
                        broadcast.live_since = now
                    if (now - broadcast.live_since).total_seconds() >= 30:
                        broadcast.attempts = 0
                else:
                    broadcast.live_since = None
                    broadcast.state = (
                        'STARTING' if broadcast.kind in {'desktop', 'page'} else 'WAITING'
                    )
                    broadcast.error = '等待采集画面或视频源发布'
                    if broadcast.kind in {'desktop', 'page'}:
                        broadcast.attempts += 1
            except AppError as error:
                broadcast.error = error.message[:256]
                broadcast.live_since = None
                broadcast.state = 'STARTING' if broadcast.kind in {'desktop', 'page'} else 'WAITING'
                if broadcast.kind in {'desktop', 'page'}:
                    broadcast.attempts += 1
            if broadcast.kind in {'desktop', 'page'} and broadcast.attempts >= 3:
                broadcast.state = 'ERROR'
                broadcast.active = False
                broadcast.stop_complete = False
                broadcast.public_token_hash = ''
                broadcast.error = '桌面采集连续失败，请检查节点组件、VNC 和媒体发布配置后重新开启'
            broadcast.save()
    finally:
        if reset_connections:
            close_old_connections()


def reconcile_all():
    ids = list(
        Broadcast.objects.filter(Q(active=True) | Q(stop_complete=False)).values_list(
            'pk', flat=True
        )[:128]
    )
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(reconcile_one, ids))
    return len(ids)
