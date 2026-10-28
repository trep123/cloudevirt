"""A separate worker keeps server browsers alive without a local browser."""

import secrets
from datetime import timedelta

from django.contrib.sessions.models import Session
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.console.broadcast_access import digest
from apps.console.models import UserWorkspace
from apps.console.workspaces import client, stop_workspace, valid
from common.errors import AppError


def reconcile_workspace(pk):
    with transaction.atomic():
        workspace = (
            UserWorkspace.objects.select_for_update(of=('self',), skip_locked=True)
            .select_related('owner')
            .filter(pk=pk)
            .first()
        )
        if workspace is None:
            return
        if workspace.active and (
            not valid(workspace)
            or (
                workspace.browser_session_key
                and not Session.objects.filter(
                    session_key=workspace.browser_session_key, expire_date__gt=timezone.now()
                ).exists()
            )
        ):
            stop_workspace(workspace)
        path = f'/api/v1/workbenches/{workspace.pk}'
        try:
            if not workspace.active:
                result = client().request_json(path, 'DELETE', {})
                if result.get('state') == 'STOPPED':
                    workspace.stop_complete = True
                    if workspace.state != 'ERROR':
                        workspace.state = 'STOPPED'
                    workspace.vnc_password = ''
                workspace.save()
                return
            result = client().get_json(path)
            if result.get('state') == 'MISSING':
                token = secrets.token_urlsafe(32)
                workspace.bootstrap_hash = digest(token)
                workspace.bootstrap_expires_at = timezone.now() + timedelta(seconds=120)
                workspace.save()
                result = client().request_json(
                    path,
                    'POST',
                    {
                        'generation': str(workspace.generation),
                        'bootstrap_token': token,
                        'owner': workspace.owner_id,
                        'vnc_password': workspace.vnc_password,
                        'expires_at': int(workspace.expires_at.timestamp()),
                    },
                )
            state = result.get('state')
            if state not in {'STARTING', 'READY'} or result.get('generation') != str(
                workspace.generation
            ):
                raise AppError('OPERATION_FAILED', '服务端浏览器启动失败，请检查工作台服务日志')
            workspace.state = state
            workspace.error = ''
            workspace.attempts = 0
        except AppError as error:
            workspace.error = error.message[:256]
            workspace.attempts += 1
            if workspace.attempts >= 3:
                stop_workspace(workspace)
                workspace.state = 'ERROR'
        workspace.save()


class Command(BaseCommand):
    help = 'Reconcile persistent shared browser workspaces'

    def handle(self, *args, **options):
        ids = UserWorkspace.objects.filter(Q(active=True) | Q(stop_complete=False)).values_list(
            'pk', flat=True
        )[:128]
        for pk in ids:
            reconcile_workspace(pk)
