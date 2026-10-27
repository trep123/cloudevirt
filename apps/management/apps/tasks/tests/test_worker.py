"""worker 执行链路测试。"""

from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from apps.nodes.models import Node
from apps.nodes.services import refresh_node
from apps.nodes.tests.fakes import FakeAgentClient
from apps.tasks.models import Task, TaskStatus, TaskType
from apps.tasks.services import enqueue
from common.errors import AppError, ErrorCode


class WorkerTests(TestCase):
    """worker 领取与执行用例。"""

    def setUp(self) -> None:
        """创建节点并注入 Agent 客户端替身。"""
        self.node = Node.objects.create(name='worker-node', endpoint='http://127.0.0.1:9100')
        self.patcher = mock.patch(
            'apps.tasks.executors.refresh_node',
            side_effect=lambda node, client=None: refresh_node(node, client=FakeAgentClient()),
        )
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_worker_executes_refresh_task(self) -> None:
        """worker 应执行刷新任务并标记成功。"""
        task = enqueue(
            task_type=TaskType.NODE_REFRESH,
            resource_type='node',
            resource_id=str(self.node.pk),
        )

        call_command('run_worker', '--once')

        task.refresh_from_db()
        self.node.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.SUCCEEDED)
        self.assertEqual(self.node.status, 'ONLINE')
        self.assertEqual(task.result['cpu_total'], 16)

    def test_worker_retries_on_recoverable_error(self) -> None:
        """可恢复错误应保留为待重试而不是直接失败。"""
        self.patcher.stop()
        failing = mock.patch(
            'apps.tasks.executors.refresh_node',
            side_effect=AppError(ErrorCode.NODE_OFFLINE, '节点离线'),
        )
        failing.start()
        self.addCleanup(failing.stop)

        task = enqueue(
            task_type=TaskType.NODE_REFRESH,
            resource_type='node',
            resource_id=str(self.node.pk),
        )

        call_command('run_worker', '--once')

        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.PENDING)
        self.assertIsNotNone(task.next_retry_at)
        self.assertEqual(task.last_error_code, ErrorCode.NODE_OFFLINE)

    def test_missing_resource_fails_task(self) -> None:
        """资源不存在时任务应失败并记录错误码。"""
        task = enqueue(
            task_type=TaskType.NODE_REFRESH,
            resource_type='node',
            resource_id='999999',
        )

        call_command('run_worker', '--once')

        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.FAILED)
        self.assertEqual(task.last_error_code, ErrorCode.NOT_FOUND)

    def test_multiple_workers_do_not_duplicate(self) -> None:
        """两个 worker 同时启动，同一任务只被执行一次。"""
        task = enqueue(
            task_type=TaskType.NODE_REFRESH,
            resource_type='node',
            resource_id=str(self.node.pk),
        )

        call_command('run_worker', '--once')
        call_command('run_worker', '--once')

        self.assertEqual(Task.objects.filter(pk=task.pk).count(), 1)
        task.refresh_from_db()
        self.assertEqual(task.attempt_count, 1)
