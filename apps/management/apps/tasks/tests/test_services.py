"""任务入队、领取、重试与恢复测试。"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.tasks.models import Task, TaskEvent, TaskStatus, TaskType
from apps.tasks.services import (
    claim_next,
    enqueue,
    mark_failed,
    mark_succeeded,
    recover_stale_tasks,
)
from common.errors import AppError, ErrorCode


class TaskServiceTests(TestCase):
    """任务服务用例。"""

    def test_enqueue_creates_pending_task(self) -> None:
        """入队应创建等待中的任务并保存参数快照。"""
        task = enqueue(
            task_type=TaskType.NODE_REFRESH,
            resource_type='node',
            resource_id='7',
            payload={'name': 'node-7'},
        )

        self.assertEqual(task.status, TaskStatus.PENDING)
        self.assertEqual(task.payload, {'name': 'node-7'})
        self.assertEqual(task.max_attempts, 3)

    def test_duplicate_active_task_is_rejected(self) -> None:
        """同资源已有未终态任务时应返回 409 语义错误。"""
        enqueue(task_type=TaskType.NODE_REFRESH, resource_type='node', resource_id='1')

        with self.assertRaises(AppError) as ctx:
            enqueue(task_type=TaskType.NODE_REFRESH, resource_type='node', resource_id='1')

        self.assertEqual(ctx.exception.code, ErrorCode.OPERATION_IN_PROGRESS)

    def test_idempotency_key_reuses_active_task(self) -> None:
        """相同幂等键的重复提交不应产生第二个任务。"""
        first = enqueue(
            task_type=TaskType.NODE_REFRESH,
            resource_type='node',
            resource_id='2',
            idempotency_key='create-vm-001',
        )
        second = enqueue(
            task_type=TaskType.NODE_REFRESH,
            resource_type='node',
            resource_id='3',
            idempotency_key='create-vm-001',
        )

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Task.objects.count(), 1)

    def test_claim_next_is_exclusive(self) -> None:
        """领取后任务变为执行中，其他 worker 不得重复领取。"""
        task = enqueue(task_type=TaskType.NODE_REFRESH, resource_type='node', resource_id='4')

        claimed = claim_next('worker-a')
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.pk, task.pk)
        self.assertEqual(claimed.status, TaskStatus.VALIDATING)
        self.assertEqual(claimed.locked_by, 'worker-a')
        self.assertIsNone(claim_next('worker-b'))

    def test_claim_skips_task_with_future_retry(self) -> None:
        """未到重试时间的任务不应被领取。"""
        task = enqueue(task_type=TaskType.NODE_REFRESH, resource_type='node', resource_id='5')
        task.status = TaskStatus.PENDING
        task.next_retry_at = timezone.now() + timedelta(seconds=60)
        task.save(update_fields=['status', 'next_retry_at'])

        self.assertIsNone(claim_next('worker-a'))

    def test_retryable_failure_is_rescheduled(self) -> None:
        """可恢复错误应重新排队并设置退避时间。"""
        task = enqueue(task_type=TaskType.NODE_REFRESH, resource_type='node', resource_id='6')
        task.attempt_count = 1
        task.save(update_fields=['attempt_count'])

        mark_failed(task, AppError(ErrorCode.NODE_OFFLINE, '节点离线'))

        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.PENDING)
        self.assertIsNotNone(task.next_retry_at)
        self.assertEqual(task.last_error_code, ErrorCode.NODE_OFFLINE)
        self.assertTrue(task.events.filter(level='ERROR').exists())

    def test_non_retryable_failure_fails_immediately(self) -> None:
        """不可恢复错误应立即失败。"""
        task = enqueue(task_type=TaskType.NODE_REFRESH, resource_type='node', resource_id='8')

        mark_failed(task, AppError(ErrorCode.VALIDATION_ERROR, '参数错误'))

        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.FAILED)
        self.assertIsNotNone(task.finished_at)

    def test_failure_after_max_attempts_is_terminal(self) -> None:
        """超过最大尝试次数后不再重试。"""
        task = enqueue(task_type=TaskType.NODE_REFRESH, resource_type='node', resource_id='9')
        task.attempt_count = 3
        task.max_attempts = 3
        task.save(update_fields=['attempt_count', 'max_attempts'])

        mark_failed(task, AppError(ErrorCode.COMMAND_TIMEOUT, '调用超时'))

        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.FAILED)
        self.assertIsNone(task.next_retry_at)

    def test_success_records_event_and_result(self) -> None:
        """成功应记录结果与事件流水。"""
        task = enqueue(task_type=TaskType.NODE_REFRESH, resource_type='node', resource_id='10')

        mark_succeeded(task, {'node_id': 10})

        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.SUCCEEDED)
        self.assertEqual(task.result, {'node_id': 10})
        self.assertTrue(task.events.filter(to_status=TaskStatus.SUCCEEDED).exists())

    def test_recovery_requeues_and_reconciles(self) -> None:
        """重启恢复应重新排队卡住的任务，并把超时创建任务转入对账。"""
        pending = enqueue(task_type=TaskType.NODE_REFRESH, resource_type='node', resource_id='11')
        creating = enqueue(
            task_type=TaskType.INSTANCE_CREATE, resource_type='instance', resource_id='12'
        )
        Task.objects.filter(pk=pending.pk).update(
            locked_by='dead-worker',
            updated_at=timezone.now() - timedelta(seconds=600),
        )
        Task.objects.filter(pk=creating.pk).update(
            status=TaskStatus.CREATING,
            locked_by='dead-worker',
            updated_at=timezone.now() - timedelta(seconds=1800),
        )

        summary = recover_stale_tasks()

        self.assertEqual(summary['requeued'], 1)
        self.assertEqual(summary['reconciling'], 1)
        pending.refresh_from_db()
        creating.refresh_from_db()
        self.assertEqual(pending.status, TaskStatus.PENDING)
        self.assertEqual(pending.locked_by, '')
        self.assertEqual(creating.status, TaskStatus.RECONCILING)
        self.assertTrue(
            TaskEvent.objects.filter(task=creating, to_status=TaskStatus.RECONCILING).exists()
        )

    def test_unregistered_task_type_fails_clearly(self) -> None:
        """未登记执行器的任务类型应明确失败而不是静默成功。"""
        task = enqueue(task_type=TaskType.RECONCILE, resource_type='instance', resource_id='13')

        from apps.tasks.executors import execute_task

        with self.assertRaises(AppError) as ctx:
            execute_task(task)

        self.assertIn('未登记执行器', str(ctx.exception))
