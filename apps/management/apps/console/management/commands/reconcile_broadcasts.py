from django.core.management.base import BaseCommand

from apps.console.broadcast_reconcile import reconcile_all


class Command(BaseCommand):
    help = '同步串流发布状态并续租服务端采集进程'

    def handle(self, *args, **options):
        self.stdout.write(f'broadcasts reconciled={reconcile_all()}')
