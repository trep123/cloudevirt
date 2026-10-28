from django.core.management.base import BaseCommand
from django.db.models import F, Q
from django.utils import timezone

from apps.console.media import close_media
from apps.console.models import ConsoleSession, MediaSession, WorkspaceControlSession
from apps.console.services import close_desktop
from common.errors import AppError


class Command(BaseCommand):
    help = '回收过期桌面和媒体连接'

    def handle(self, *args, **options):
        desktop = media = 0
        from apps.console.workspaces import client

        for session in WorkspaceControlSession.objects.filter(
            revoked=False, expires_at__lte=timezone.now()
        )[:100]:
            try:
                client().request_json(f'/api/v1/console-sessions/{session.pk}', 'DELETE', {})
                session.revoked = True
                session.save(update_fields=['revoked'])
            except AppError:
                continue
        for session in ConsoleSession.objects.filter(
            revoked=False, expires_at__lte=timezone.now()
        ).select_related('instance__node')[:100]:
            close_desktop(session)
            desktop += 1
        invalid_public = Q(broadcast__isnull=False) & (
            Q(broadcast__active=False)
            | Q(broadcast__link_expires_at__lte=timezone.now())
            | ~Q(access_version=F('broadcast__access_version'))
        )
        for session in MediaSession.objects.filter(
            Q(expires_at__lte=timezone.now()) | invalid_public, closed=False
        )[:100]:
            try:
                close_media(session)
                media += 1
            except AppError:
                continue
        self.stdout.write(f'closed desktop={desktop}, media={media}')
