from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.console.models import ConsoleSession
from apps.console.services import close_desktop


class Command(BaseCommand):
    help = '回收过期虚拟机控制台连接'

    def handle(self, *args, **options):
        closed = 0
        for session in ConsoleSession.objects.filter(
            revoked=False, expires_at__lte=timezone.now()
        ).select_related('instance__node')[:100]:
            close_desktop(session)
            closed += 1
        self.stdout.write(f'closed desktop={closed}')
