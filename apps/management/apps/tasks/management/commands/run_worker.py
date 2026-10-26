"""任务 worker：原子领取并执行任务，支持有限重试。

用法:
  python manage.py run_worker                 # 常驻循环
  python manage.py run_worker --once          # 只跑一轮（测试/一次执行）
  python manage.py run_worker --max-tasks 10  # 限制本轮最多执行数量
"""

import logging
import os
import socket
import time

from django.core.management.base import BaseCommand

from apps.tasks.executors import execute_task
from apps.tasks.services import (
    claim_next,
    mark_failed,
    mark_succeeded,
    recover_stale_tasks,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """循环领取并执行任务。"""

    help = '领取并执行异步任务（可由 systemd 常驻）'

    def add_arguments(self, parser) -> None:
        """注册命令行参数。"""
        parser.add_argument('--once', action='store_true', help='只执行一轮后退出')
        parser.add_argument(
            '--max-tasks', type=int, default=0, help='本轮最多执行任务数，0 表示不限'
        )
        parser.add_argument('--sleep', type=float, default=2.0, help='空闲时的等待秒数')

    def handle(self, *args, **options) -> None:
        """启动循环：先恢复遗留任务，再持续领取执行。"""
        worker_id = f'{socket.gethostname()}:{os.getpid()}'
        recovery = recover_stale_tasks()
        if recovery['requeued'] or recovery['reconciling']:
            self.stdout.write(f'恢复任务: {recovery}')

        executed = 0
        while True:
            task = claim_next(worker_id)
            if task is None:
                if options['once']:
                    break
                time.sleep(options['sleep'])
                continue

            try:
                result = execute_task(task)
            except Exception as exc:
                mark_failed(task, exc)
                self.stdout.write(self.style.WARNING(f'任务失败: {task.pk} {exc}'))
            else:
                mark_succeeded(task, result)
                self.stdout.write(self.style.SUCCESS(f'任务完成: {task.pk}'))

            executed += 1
            if options['once'] or (options['max_tasks'] and executed >= options['max_tasks']):
                break

        self.stdout.write(f'本轮执行任务数: {executed}')
