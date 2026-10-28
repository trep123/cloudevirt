from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.console.media import close_media
from apps.console.models import ConsoleSession, MediaSession
from apps.console.services import close_desktop
from common.errors import AppError


class Command(BaseCommand):
    help = '回收过期桌面和媒体连接'

    def handle(self, *args, **options):
        desktop = media = 0
        for session in ConsoleSession.objects.filter(
            revoked=False, expires_at__lte=timezone.now()
        ).select_related('instance__node')[:100]:
            close_desktop(session)
            desktop += 1
        for session in MediaSession.objects.filter(closed=False, expires_at__lte=timezone.now())[
            :100
        ]:
            try:
                close_media(session)
                media += 1
            except AppError:
                continue
        self.stdout.write(f'closed desktop={desktop}, media={media}')
