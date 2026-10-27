"""监控、告警与对账模型。

对账只做检测与安全修复，有破坏风险的差异进入人工处理（不自动删除）。
"""

from django.db import models


class AlertType(models.TextChoices):
    """告警类型。"""

    NODE_OFFLINE = 'NODE_OFFLINE', '节点离线'
    RESOURCE_LOW = 'RESOURCE_LOW', '资源不足'
    TASK_STUCK = 'TASK_STUCK', '任务长时间未结束'
    DISK_SPACE_LOW = 'DISK_SPACE_LOW', '磁盘空间低'
    LIBVIRT_UNAVAILABLE = 'LIBVIRT_UNAVAILABLE', 'libvirt 不可用'
    DB_INSTANCE_MISSING_DOMAIN = 'DB_INSTANCE_MISSING_DOMAIN', '数据库实例缺少对应域'
    DOMAIN_NOT_IN_DB = 'DOMAIN_NOT_IN_DB', '存在未登记的域'
    INSTANCE_STATE_DRIFT = 'INSTANCE_STATE_DRIFT', '实例状态漂移'
    RESERVATION_MISMATCH = 'RESERVATION_MISMATCH', '资源预留过期'
    DISK_FILE_MISSING = 'DISK_FILE_MISSING', '磁盘文件缺失'
    DISK_NOT_IN_DB = 'DISK_NOT_IN_DB', '存在未登记的磁盘文件'
    DISK_SIZE_MISMATCH = 'DISK_SIZE_MISMATCH', '磁盘容量与记录不一致'


class AlertLevel(models.TextChoices):
    """告警级别。"""

    INFO = 'INFO', '提示'
    WARNING = 'WARNING', '警告'
    CRITICAL = 'CRITICAL', '严重'


class AlertStatus(models.TextChoices):
    """告警状态。"""

    ACTIVE = 'ACTIVE', '活跃'
    ACKED = 'ACKED', '已确认'
    RESOLVED = 'RESOLVED', '已恢复'


class Alert(models.Model):
    """告警记录，同类告警按资源聚合计数。"""

    type = models.CharField('类型', max_length=32, choices=AlertType.choices)
    level = models.CharField(
        '级别', max_length=16, choices=AlertLevel.choices, default=AlertLevel.WARNING
    )
    node = models.ForeignKey(
        'nodes.Node',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='alerts',
        verbose_name='节点',
    )
    instance = models.ForeignKey(
        'instances.Instance',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='alerts',
        verbose_name='实例',
    )
    resource_type = models.CharField('资源类型', max_length=32, blank=True, default='')
    resource_id = models.CharField('资源标识', max_length=64, blank=True, default='')
    message = models.TextField('说明')
    status = models.CharField(
        '状态', max_length=16, choices=AlertStatus.choices, default=AlertStatus.ACTIVE
    )
    count = models.PositiveIntegerField('累计次数', default=1)
    first_seen_at = models.DateTimeField('首次出现', auto_now_add=True)
    last_seen_at = models.DateTimeField('最近出现', auto_now=True)
    resolved_at = models.DateTimeField('恢复时间', null=True, blank=True)

    class Meta:
        verbose_name = '告警'
        verbose_name_plural = '告警'
        ordering = ['-last_seen_at']
        indexes = [models.Index(fields=['status', 'level', 'last_seen_at'])]

    def __str__(self) -> str:
        """返回可读标识。"""
        return f'{self.type} {self.status} ({self.resource_type}:{self.resource_id})'


class ReconciliationRun(models.Model):
    """一次对账执行。"""

    started_at = models.DateTimeField('开始时间', auto_now_add=True)
    finished_at = models.DateTimeField('结束时间', null=True, blank=True)
    status = models.CharField('状态', max_length=16, default='RUNNING')
    scope = models.CharField('范围', max_length=64, blank=True, default='')
    summary = models.JSONField('汇总', default=dict, blank=True)
    error_message = models.TextField('错误信息', blank=True, default='')

    class Meta:
        verbose_name = '对账执行'
        verbose_name_plural = '对账执行'
        ordering = ['-started_at']
        permissions = [('run_reconciliation', '可以触发对账')]

    def __str__(self) -> str:
        """返回可读标识。"""
        return f'run-{self.pk} {self.status}'


class DiffKind(models.TextChoices):
    """对账差异类型。"""

    DB_INSTANCE_MISSING_DOMAIN = 'DB_INSTANCE_MISSING_DOMAIN', '数据库实例缺少对应域'
    DOMAIN_NOT_IN_DB = 'DOMAIN_NOT_IN_DB', '存在未登记的域'
    INSTANCE_STATE_DRIFT = 'INSTANCE_STATE_DRIFT', '实例状态漂移'
    RESERVATION_MISMATCH = 'RESERVATION_MISMATCH', '资源预留过期'
    DISK_FILE_MISSING = 'DISK_FILE_MISSING', '磁盘文件缺失'
    DISK_NOT_IN_DB = 'DISK_NOT_IN_DB', '存在未登记的磁盘文件'
    DISK_SIZE_MISMATCH = 'DISK_SIZE_MISMATCH', '磁盘容量与记录不一致'


class DiffResolution(models.TextChoices):
    """差异处理状态。"""

    PENDING = 'PENDING', '待处理'
    AUTO_FIXED = 'AUTO_FIXED', '已自动修复'
    MANUAL = 'MANUAL', '需人工处理'
    IGNORED = 'IGNORED', '已忽略'


class ReconciliationDiff(models.Model):
    """对账单条差异。"""

    run = models.ForeignKey(
        ReconciliationRun,
        on_delete=models.CASCADE,
        related_name='diffs',
        verbose_name='对账执行',
        null=True,
        blank=True,
    )
    kind = models.CharField('类型', max_length=32, choices=DiffKind.choices)
    node = models.ForeignKey(
        'nodes.Node',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reconciliation_diffs',
        verbose_name='节点',
    )
    resource_type = models.CharField('资源类型', max_length=32, blank=True, default='')
    resource_id = models.CharField('资源标识', max_length=64, blank=True, default='')
    detail = models.JSONField('详情', default=dict, blank=True)
    resolution = models.CharField(
        '处理状态', max_length=16, choices=DiffResolution.choices, default=DiffResolution.PENDING
    )
    resolved_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_diffs',
        verbose_name='处理人',
    )
    resolved_at = models.DateTimeField('处理时间', null=True, blank=True)
    note = models.TextField('处理说明', blank=True, default='')

    class Meta:
        verbose_name = '对账差异'
        verbose_name_plural = '对账差异'
        ordering = ['id']
        indexes = [models.Index(fields=['run', 'kind']), models.Index(fields=['resolution'])]

    def __str__(self) -> str:
        """返回可读标识。"""
        return f'{self.kind} {self.resource_type}:{self.resource_id}'
