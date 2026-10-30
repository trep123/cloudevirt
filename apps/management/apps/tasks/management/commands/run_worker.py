"""任务 worker：原子领取并执行任务，支持有限重试。

用法:
  python manage.py run_worker                 # 常驻循环
  python manage.py run_worker --once          # 只跑一轮（测试/一次执行）
  python manage.py run_worker --max-tasks 10  # 限制本轮最多执行数量
"""

import logging
import os
import signal
import socket
import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections, connections

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
        parser.add_argument('--sleep', type=float, default=0.5, help='空闲时的等待秒数')
        parser.add_argument(
            '--concurrency',
            type=int,
            default=int(os.environ.get('CLOUDVIRT_WORKER_CONCURRENCY', '2')),
            help='并行任务数 1–8，默认 2；同一资源仍串行',
        )

    def handle(self, *args, **options) -> None:
        """启动循环：先恢复遗留任务，再持续领取执行。"""
        if not 1 <= options['concurrency'] <= 8 or options['sleep'] <= 0:
            raise CommandError('concurrency 必须为 1–8，sleep 必须大于 0')
        worker_id = f'{socket.gethostname()}:{os.getpid()}'
        recovery = recover_stale_tasks()
        if recovery['requeued'] or recovery['reconciling']:
            self.stdout.write(f'恢复任务: {recovery}')

        if options['once']:
            task = claim_next(worker_id)
            if task is not None:
                self.process_task(task)
            return

        stopping = threading.Event()
        previous = {}
        if threading.current_thread() is threading.main_thread():
            for signum in (signal.SIGTERM, signal.SIGINT):
                previous[signum] = signal.getsignal(signum)
                signal.signal(signum, lambda *_: stopping.set())
        submitted = 0
        pending = set()
        try:
            with ThreadPoolExecutor(max_workers=options['concurrency']) as pool:
                while not stopping.is_set():
                    done = {future for future in pending if future.done()}
                    for future in done:
                        future.result()
                    pending -= done
                    if options['max_tasks'] and submitted >= options['max_tasks']:
                        break
                    if len(pending) >= options['concurrency']:
                        wait(pending, timeout=options['sleep'], return_when=FIRST_COMPLETED)
                        continue
                    close_old_connections()
                    task = claim_next(worker_id)
                    if task is None:
                        stopping.wait(options['sleep'])
                        continue
                    pending.add(pool.submit(self.execute_thread, task))
                    submitted += 1
                for future in pending:
                    future.result()
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)
        self.stdout.write(f'本轮执行任务数: {submitted}')

    def execute_thread(self, task):
        close_old_connections()
        try:
            self.process_task(task)
        finally:
            connections.close_all()

    def process_task(self, task):
        try:
            result = execute_task(task)
        except Exception as exc:
            mark_failed(task, exc)
            self.stdout.write(self.style.WARNING(f'任务失败: {task.pk} {exc}'))
        else:
            mark_succeeded(task, result)
            self.stdout.write(self.style.SUCCESS(f'任务完成: {task.pk}'))
