from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import AccountBatch, LoginRateBucket


class Command(BaseCommand):
    help = '清理过期账号导入预览及导出文件，保留批次审计元数据'

    def handle(self, *args, **options):
        count = (
            AccountBatch.objects.filter(expires_at__lte=timezone.now())
            .exclude(state='RUNNING')
            .update(rows=[], results=[], file_data=None, state='EXPIRED')
        )
        self.stdout.write(f'Expired account batches cleared: {count}')
        expired, _ = LoginRateBucket.objects.filter(expires_at__lte=timezone.now()).delete()
        self.stdout.write(f'Expired login counters cleared: {expired}')
