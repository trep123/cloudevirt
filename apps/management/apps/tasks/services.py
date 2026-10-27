"""任务入队、原子领取、重试与恢复。

并发控制要点：
- 领取使用 select_for_update(skip_locked=True)，多 worker 不会重复领取；
- 同一资源只允许一个未终态任务（数据库条件唯一约束 + 显式校验）；
- 仅可恢复错误重试，且重试前确认幂等。
"""

import logging
from datetime import timedelta

from django.db import DatabaseError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.tasks.models import (
    ACTIVE_STATUSES,
    RETRYABLE_ERROR_CODES,
    Task,
    TaskEvent,
    TaskStatus,
)
from common.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)

# 领取后未释放的锁超时时间，用于崩溃恢复
LOCK_TIMEOUT_SECONDS = 300


def enqueue(
    *,
    task_type: str,
    resource_type: str,
    resource_id: str,
    requested_by=None,
    payload: dict | None = None,
    idempotency_key: str | None = None,
    max_attempts: int = 3,
) -> Task:
    """创建任务；相同幂等键的活跃任务直接复用。

    Args:
        task_type: 任务类型。
        resource_type: 资源类型。
        resource_id: 资源标识。
        requested_by: 发起人。
        payload: 请求参数快照（禁止含密钥）。
        idempotency_key: 幂等键。
        max_attempts: 最大尝试次数。

    Returns:
        新建或已存在的任务。

    Raises:
        AppError: 同资源已存在未终态任务时抛出 OPERATION_IN_PROGRESS。
    """
    active = Task.objects.filter(
        resource_type=resource_type, resource_id=str(resource_id), status__in=list(ACTIVE_STATUSES)
    ).first()
    if active is not None:
        raise AppError(
            ErrorCode.OPERATION_IN_PROGRESS,
            '该资源存在未结束的任务',
            details={'task_id': str(active.pk), 'status': active.status},
        )

    if idempotency_key:
        existing = Task.objects.filter(
            idempotency_key=idempotency_key, status__in=list(ACTIVE_STATUSES)
        ).first()
        if existing is not None:
            return existing

    try:
        with transaction.atomic():
            return Task.objects.create(
                type=task_type,
                resource_type=resource_type,
                resource_id=str(resource_id),
                requested_by=requested_by if requested_by and requested_by.pk else None,
                payload=payload or {},
                idempotency_key=idempotency_key or '',
                max_attempts=max_attempts,
            )
    except DatabaseError as exc:
        logger.warning('任务入队冲突', exc_info=True)
        raise AppError(
            ErrorCode.OPERATION_IN_PROGRESS,
            '任务已存在或正在处理',
        ) from exc


def claim_next(worker_id: str) -> Task | None:
    """原子领取一个可执行任务。

    Args:
        worker_id: 领取者标识。

    Returns:
        领取到的任务；无可执行任务时返回 None。
    """
    now = timezone.now()
    with transaction.atomic():
        candidate = (
            Task.objects.select_for_update(skip_locked=True)
            .filter(status__in=[TaskStatus.PENDING, TaskStatus.RECONCILING])
            .filter(Q(next_retry_at__isnull=True) | Q(next_retry_at__lte=now))
            .order_by('created_at')
            .first()
        )
        if candidate is None:
            return None
        candidate.attempt_count += 1
        candidate.status = TaskStatus.VALIDATING
        candidate.locked_at = now
        candidate.locked_by = worker_id
        candidate.next_retry_at = None
        candidate.started_at = candidate.started_at or now
        candidate.save(
            update_fields=[
                'status',
                'attempt_count',
                'locked_at',
                'locked_by',
                'next_retry_at',
                'started_at',
                'updated_at',
            ]
        )
        record_event(
            candidate,
            to_status=TaskStatus.VALIDATING,
            message=f'任务被 {worker_id} 领取',
            attempt=candidate.attempt_count,
        )
        return candidate


def record_event(
    task: Task,
    *,
    to_status: str = '',
    from_status: str = '',
    message: str = '',
    level: str = 'INFO',
    error_code: str = '',
    attempt: int | None = None,
) -> TaskEvent:
    """写入任务事件流水。"""
    return TaskEvent.objects.create(
        task=task,
        attempt=attempt if attempt is not None else task.attempt_count,
        from_status=from_status or task.status,
        to_status=to_status,
        level=level,
        error_code=error_code,
        message=message,
    )


def mark_succeeded(task: Task, result: dict | None = None) -> Task:
    """标记任务成功。"""
    now = timezone.now()
    task.status = TaskStatus.SUCCEEDED
    task.result = result or {}
    task.finished_at = now
    task.locked_at = None
    task.locked_by = ''
    task.next_retry_at = None
    task.last_error_code = ''
    task.last_error_message = ''
    task.save()
    record_event(task, to_status=TaskStatus.SUCCEEDED, message='任务执行成功')
    return task


def mark_failed(task: Task, error: Exception) -> Task:
    """标记任务失败；可恢复错误在次数内改为等待重试。

    Args:
        task: 目标任务。
        error: 执行过程中抛出的异常。

    Returns:
        更新后的任务。
    """
    code = getattr(error, 'code', ErrorCode.OPERATION_FAILED)
    message = str(error)
    retryable = code in RETRYABLE_ERROR_CODES and task.attempt_count < task.max_attempts

    record_event(
        task,
        to_status=TaskStatus.PENDING if retryable else TaskStatus.FAILED,
        message=message,
        level='ERROR',
        error_code=code,
    )

    task.last_error_code = code
    task.last_error_message = message
    if retryable:
        backoff = 10 * task.attempt_count
        task.status = TaskStatus.PENDING
        task.next_retry_at = timezone.now() + timedelta(seconds=backoff)
        task.locked_at = None
        task.locked_by = ''
        task.save(
            update_fields=[
                'status',
                'last_error_code',
                'last_error_message',
                'next_retry_at',
                'locked_at',
                'locked_by',
                'updated_at',
            ]
        )
        logger.warning(
            '任务将重试',
            extra={'task_id': str(task.pk), 'attempt': task.attempt_count, 'code': code},
        )
        return task

    task.status = TaskStatus.FAILED
    task.finished_at = timezone.now()
    task.locked_at = None
    task.locked_by = ''
    task.next_retry_at = None
    task.save()
    logger.error('任务失败', extra={'task_id': str(task.pk), 'code': code})
    return task


def recover_stale_tasks(
    *, pending_after_seconds: int = 300, creating_after_seconds: int = 900
) -> dict[str, int]:
    """服务重启后的任务恢复。

    - 长期停留在 PENDING/VALIDATING 且锁已过期的任务重新排队；
    - 长期停留在 CREATING 的任务转入 RECONCILING，先查询实际状态再决定后续。

    Args:
        pending_after_seconds: 判定 PENDING 卡住的时长。
        creating_after_seconds: 判定 CREATING 卡住的时长。

    Returns:
        形如 {'requeued': n, 'reconciling': n} 的汇总。
    """
    now = timezone.now()
    summary = {'requeued': 0, 'reconciling': 0}

    stale_pending = Task.objects.filter(
        status__in=[TaskStatus.PENDING, TaskStatus.VALIDATING],
        updated_at__lte=now - timedelta(seconds=pending_after_seconds),
    )
    for task in stale_pending:
        if task.type == 'INSTANCE_SNAPSHOT' and task.status == TaskStatus.VALIDATING:
            # A terminated worker may already have changed disk contents.
            task.max_attempts = task.attempt_count
            mark_failed(
                task,
                AppError(
                    ErrorCode.CONFLICT,
                    '快照任务执行中断，结果未知；请查询实际快照状态，禁止自动重放',
                ),
            )
            continue
        task.status = TaskStatus.PENDING
        task.locked_at = None
        task.locked_by = ''
        task.next_retry_at = None
        task.save(update_fields=['status', 'locked_at', 'locked_by', 'next_retry_at', 'updated_at'])
        record_event(task, to_status=TaskStatus.PENDING, message='服务重启后重新排队')
        summary['requeued'] += 1

    stuck_creating = Task.objects.filter(
        status=TaskStatus.CREATING,
        updated_at__lte=now - timedelta(seconds=creating_after_seconds),
    )
    for task in stuck_creating:
        task.status = TaskStatus.RECONCILING
        task.locked_at = None
        task.locked_by = ''
        task.save(update_fields=['status', 'locked_at', 'locked_by', 'updated_at'])
        record_event(task, to_status=TaskStatus.RECONCILING, message='创建超时，转入对账')
        summary['reconciling'] += 1

    if summary['requeued'] or summary['reconciling']:
        logger.info('任务恢复完成', extra=summary)
    return summary
