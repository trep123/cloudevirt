"""异步任务模型与状态字典。

任务由 API 入队，由独立 worker 原子领取并执行；
同一资源在同一时刻只允许存在一个未终态任务。
"""

import uuid

from django.conf import settings
from django.db import models


class TaskStatus(models.TextChoices):
    """任务状态。"""

    PENDING = 'PENDING', '等待执行'
    VALIDATING = 'VALIDATING', '校验中'
    PREPARING = 'PREPARING', '准备中'
    CREATING = 'CREATING', '创建中'
    VERIFYING = 'VERIFYING', '校验结果中'
    SUCCEEDED = 'SUCCEEDED', '成功'
    FAILED = 'FAILED', '失败'
    CANCELLED = 'CANCELLED', '已取消'
    RECONCILING = 'RECONCILING', '对账中'


class TaskType(models.TextChoices):
    """任务类型。"""

    NODE_REFRESH = 'NODE_REFRESH', '刷新节点资源'
    INSTANCE_CREATE = 'INSTANCE_CREATE', '创建虚拟机'
    INSTANCE_START = 'INSTANCE_START', '启动虚拟机'
    INSTANCE_SHUTDOWN = 'INSTANCE_SHUTDOWN', '关闭虚拟机'
    INSTANCE_FORCE_STOP = 'INSTANCE_FORCE_STOP', '强制停止虚拟机'
    INSTANCE_REBOOT = 'INSTANCE_REBOOT', '重启虚拟机'
    INSTANCE_DELETE = 'INSTANCE_DELETE', '删除虚拟机'
    IMAGE_IMPORT = 'IMAGE_IMPORT', '导入镜像'
    IMAGE_DELETE = 'IMAGE_DELETE', '删除镜像'
    RECONCILE = 'RECONCILE', '状态对账'
    STORAGE_POOL_CREATE = 'STORAGE_POOL_CREATE', '创建存储池'
    INSTANCE_SNAPSHOT = 'INSTANCE_SNAPSHOT', '虚拟机快照'


# 未终态：可被执行、参与互斥判断与幂等唯一约束
ACTIVE_STATUSES = frozenset(
    {
        TaskStatus.PENDING,
        TaskStatus.VALIDATING,
        TaskStatus.PREPARING,
        TaskStatus.CREATING,
        TaskStatus.VERIFYING,
        TaskStatus.RECONCILING,
    }
)

# 终态：不再变更
TERMINAL_STATUSES = frozenset(
    {
        TaskStatus.SUCCEEDED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    }
)

# 可恢复错误：允许有限次重试
RETRYABLE_ERROR_CODES = frozenset(
    {
        'NODE_OFFLINE',
        'COMMAND_TIMEOUT',
        'LIBVIRT_UNAVAILABLE',
    }
)


class Task(models.Model):
    """异步任务。"""

    id = models.UUIDField('任务 ID', primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField('类型', max_length=32, choices=TaskType.choices)
    status = models.CharField(
        '状态', max_length=16, choices=TaskStatus.choices, default=TaskStatus.PENDING
    )
    resource_type = models.CharField('资源类型', max_length=32)
    resource_id = models.CharField('资源标识', max_length=64)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tasks',
        verbose_name='发起人',
    )
    idempotency_key = models.CharField('幂等键', max_length=64, blank=True, default='')
    payload = models.JSONField('请求快照', default=dict, blank=True)
    result = models.JSONField('执行结果', null=True, blank=True)

    attempt_count = models.PositiveIntegerField('已尝试次数', default=0)
    max_attempts = models.PositiveIntegerField('最大尝试次数', default=3)
    next_retry_at = models.DateTimeField('下次重试时间', null=True, blank=True)
    locked_at = models.DateTimeField('领取时间', null=True, blank=True)
    locked_by = models.CharField('领取者', max_length=64, blank=True, default='')

    started_at = models.DateTimeField('开始时间', null=True, blank=True)
    finished_at = models.DateTimeField('结束时间', null=True, blank=True)
    last_error_code = models.CharField('最近错误码', max_length=64, blank=True, default='')
    last_error_message = models.TextField('最近错误信息', blank=True, default='')
    parent_task = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='父任务'
    )
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '任务'
        verbose_name_plural = '任务'
        ordering = ['-created_at']
        permissions = [
            ('cancel_task', '可以取消未开始的任务'),
            ('retry_task', '可以重试失败的任务'),
        ]
        indexes = [
            models.Index(fields=['status', 'next_retry_at']),
            models.Index(fields=['resource_type', 'resource_id', 'status']),
            models.Index(fields=['created_at']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['resource_type', 'resource_id'],
                condition=models.Q(status__in=sorted(ACTIVE_STATUSES)),
                name='uniq_active_task_per_resource',
            ),
            models.UniqueConstraint(
                fields=['idempotency_key'],
                condition=models.Q(status__in=sorted(ACTIVE_STATUSES))
                & ~models.Q(idempotency_key=''),
                name='uniq_active_idempotency_key',
            ),
        ]

    def __str__(self) -> str:
        """返回可读标识。"""
        return f'{self.type}:{self.resource_id} {self.status}'

    @property
    def is_active(self) -> bool:
        """是否处于未终态。"""
        return self.status in ACTIVE_STATUSES


class TaskEvent(models.Model):
    """任务事件流水，用于追踪尝试与状态迁移。"""

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='events')
    attempt = models.PositiveIntegerField('尝试序号', default=0)
    from_status = models.CharField('原状态', max_length=16, blank=True, default='')
    to_status = models.CharField('新状态', max_length=16, blank=True, default='')
    level = models.CharField('级别', max_length=16, default='INFO')
    error_code = models.CharField('错误码', max_length=64, blank=True, default='')
    message = models.TextField('说明', blank=True, default='')
    created_at = models.DateTimeField('发生时间', auto_now_add=True)

    class Meta:
        verbose_name = '任务事件'
        verbose_name_plural = '任务事件'
        ordering = ['created_at']
        indexes = [models.Index(fields=['task', 'created_at'])]

    def __str__(self) -> str:
        """返回可读标识。"""
        return f'{self.task_id} {self.from_status}->{self.to_status} {self.level}'
