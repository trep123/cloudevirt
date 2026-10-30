"""节点模型与状态字典。

节点记录是平台侧的登记信息，资源字段是最近一次成功采集的快照，
必须配合采样时间与过期标记使用，不得当作实时值。
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class NodeStatus(models.TextChoices):
    """节点状态。"""

    UNKNOWN = 'UNKNOWN', '未知'
    ONLINE = 'ONLINE', '在线'
    DEGRADED = 'DEGRADED', '降级'
    OFFLINE = 'OFFLINE', '离线'
    MAINTENANCE = 'MAINTENANCE', '维护中'


class Node(models.Model):
    """KVM 宿主机节点。"""

    name = models.CharField('名称', max_length=64, unique=True)
    endpoint = models.CharField(
        'Agent 地址', max_length=255, help_text='形如 http://10.0.0.11:9100'
    )
    status = models.CharField(
        '状态', max_length=16, choices=NodeStatus.choices, default=NodeStatus.UNKNOWN
    )
    maintenance_note = models.TextField('维护说明', blank=True, default='')
    agent_version = models.CharField('Agent 版本', max_length=32, blank=True, default='')

    cpu_usage_percent = models.FloatField('CPU 使用率', null=True, blank=True)
    cpu_sampled_at = models.DateTimeField('CPU 采样时间', null=True, blank=True)
    cpu_total = models.PositiveIntegerField('逻辑 CPU 数', null=True, blank=True)
    memory_total_mib = models.PositiveIntegerField('内存总量(MiB)', null=True, blank=True)
    memory_available_mib = models.PositiveIntegerField('可用内存(MiB)', null=True, blank=True)
    storage_total_bytes = models.BigIntegerField('存储总容量(字节)', null=True, blank=True)
    storage_free_bytes = models.BigIntegerField('存储剩余(字节)', null=True, blank=True)
    resource_sampled_at = models.DateTimeField('资源采样时间', null=True, blank=True)
    resource_is_stale = models.BooleanField('资源数据已过期', default=True)

    last_seen_at = models.DateTimeField('最近心跳时间', null=True, blank=True)
    consecutive_failures = models.PositiveIntegerField('连续采集失败次数', default=0)
    last_error_code = models.CharField('最近错误码', max_length=64, blank=True, default='')
    last_error_message = models.TextField('最近错误信息', blank=True, default='')

    heartbeat_interval_seconds = models.PositiveIntegerField('采集周期(秒)', default=30)
    offline_after_seconds = models.PositiveIntegerField('离线判定阈值(秒)', default=90)

    is_deleted = models.BooleanField('已注销', default=False)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '节点'
        verbose_name_plural = '节点'
        ordering = ['name']
        permissions = [('refresh_node', '可以主动刷新节点资源')]
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['last_seen_at']),
            models.Index(fields=['is_deleted', 'status']),
        ]

    def __str__(self) -> str:
        """返回可读标识。"""
        return f'{self.name} ({self.status})'

    @property
    def is_schedulable(self) -> bool:
        """是否可作为新实例的调度目标（由状态派生，不单独落库）。"""
        return not self.is_deleted and self.status in {
            NodeStatus.ONLINE,
            NodeStatus.DEGRADED,
        }

    @property
    def is_offline(self) -> bool:
        """是否已判定离线。"""
        return self.status == NodeStatus.OFFLINE

    def mark_offline_if_expired(self, now=None) -> bool:
        """按阈值判定离线，维护态不被自动改写。

        Args:
            now: 当前时间，默认取系统时间。

        Returns:
            是否将状态改为离线。
        """
        if self.status == NodeStatus.MAINTENANCE:
            return False
        current = now or timezone.now()
        expired_by_count = (
            self.consecutive_failures * self.heartbeat_interval_seconds
            >= self.offline_after_seconds
        )
        expired_by_time = bool(
            self.last_seen_at
            and (current - self.last_seen_at).total_seconds() >= self.offline_after_seconds
        )
        if expired_by_count or expired_by_time:
            self.status = NodeStatus.OFFLINE
            return True
        return False


class NodePermission(models.TextChoices):
    """节点对象级权限。"""

    VIEW = 'VIEW', '查看'
    OPERATE = 'OPERATE', '操作（创建/刷新/生命周期）'


class NodeAccess(models.Model):
    """节点对象级授权记录。"""

    node = models.ForeignKey(
        Node, on_delete=models.CASCADE, related_name='access_rules', verbose_name='节点'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='node_access',
        verbose_name='用户',
    )
    group = models.ForeignKey(
        'auth.Group',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='node_access',
        verbose_name='用户组',
    )
    permission = models.CharField(
        '权限', max_length=16, choices=NodePermission.choices, default=NodePermission.OPERATE
    )
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '节点授权'
        verbose_name_plural = '节点授权'
        ordering = ['node', 'user', 'group']
        constraints = [
            models.CheckConstraint(
                name='node_access_target_required',
                condition=models.Q(user__isnull=False) | models.Q(group__isnull=False),
            )
        ]
        indexes = [models.Index(fields=['node', 'permission'])]

    def __str__(self) -> str:
        """返回可读标识。"""
        target = self.user or self.group
        return f'{self.node} -> {target} ({self.permission})'
