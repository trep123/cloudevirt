"""对所有节点执行一次心跳采集（由 systemd timer 或 cron 周期调用）。"""

from django.core.management.base import BaseCommand

from apps.nodes.services import collect_all_nodes


class Command(BaseCommand):
    """周期采集节点状态与资源。"""

    help = '采集全部节点的心跳与资源（用于 systemd timer / cron 周期调用）'

    def handle(self, *args, **options) -> None:
        """执行一轮采集并输出汇总。"""
        summary = collect_all_nodes()
        self.stdout.write(
            self.style.SUCCESS(
                '节点采集完成: 总计 {total} 在线 {online} 离线 {offline} 异常 {failed}'.format(
                    **summary
                )
            )
        )
