"""周期对账命令（由 systemd timer / cron 调用）。"""

from django.core.management.base import BaseCommand

from apps.monitoring.services import run_reconciliation


class Command(BaseCommand):
    """执行一次全量对账并输出汇总。"""

    help = '对全部节点执行一次状态对账'

    def handle(self, *args, **options) -> None:
        """执行对账。"""
        run = run_reconciliation()
        self.stdout.write(
            self.style.SUCCESS(f'对账完成: {run.status} {run.summary}'),
        )
