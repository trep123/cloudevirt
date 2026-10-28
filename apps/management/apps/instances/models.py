"""虚拟机实例、磁盘与资源预留模型。

三种状态严格分离：desired_state（期望）、observed_state（观测）、
operation_status（当前任务阶段），不得合并到同一字段。
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class ObservedState(models.TextChoices):
    """从 libvirt 观测到的实际状态。"""

    SHUTOFF = 'SHUTOFF', '已关机'
    RUNNING = 'RUNNING', '运行中'
    PAUSED = 'PAUSED', '已暂停'
    CRASHED = 'CRASHED', '已崩溃'
    UNKNOWN = 'UNKNOWN', '未知'


class DesiredState(models.TextChoices):
    """用户期望状态。"""

    RUNNING = 'RUNNING', '运行'
    SHUTOFF = 'SHUTOFF', '关机'


class DiskRole(models.TextChoices):
    """磁盘角色。"""

    SYSTEM = 'SYSTEM', '系统盘'
    DATA = 'DATA', '数据盘'


class DiskStatus(models.TextChoices):
    """磁盘状态。"""

    CREATING = 'CREATING', '创建中'
    READY = 'READY', '就绪'
    DELETING = 'DELETING', '删除中'
    DELETED = 'DELETED', '已删除'
    FAILED = 'FAILED', '失败'


class ReservationStatus(models.TextChoices):
    """资源预留状态。"""

    HELD = 'HELD', '已预留'
    COMMITTED = 'COMMITTED', '已分配'
    RELEASED = 'RELEASED', '已释放'
    EXPIRED = 'EXPIRED', '已过期'


class Instance(models.Model):
    """虚拟机实例。"""

    uuid = models.UUIDField('UUID', default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField('名称', max_length=64)
    libvirt_domain_name = models.CharField('libvirt 域名', max_length=128)
    node = models.ForeignKey(
        'nodes.Node', on_delete=models.PROTECT, related_name='instances', verbose_name='节点'
    )
    image = models.ForeignKey(
        'images.Image', on_delete=models.PROTECT, related_name='instances', verbose_name='镜像'
    )
    network_name = models.CharField('网络名称', max_length=64, blank=True, default='')
    vnc_password = models.CharField('VNC 口令', max_length=16, blank=True, default='')

    vcpu = models.PositiveIntegerField('vCPU')
    memory_mib = models.PositiveIntegerField('内存(MiB)')
    disk_gib = models.PositiveIntegerField('系统盘(GiB)')
    autostart = models.BooleanField('开机自启', default=False)
    creation_config = models.JSONField(default=dict, blank=True)
    initialization_status = models.CharField(max_length=20, default='NOT_CONFIGURED')

    desired_state = models.CharField(
        '期望状态', max_length=16, choices=DesiredState.choices, default=DesiredState.RUNNING
    )
    observed_state = models.CharField(
        '观测状态', max_length=16, choices=ObservedState.choices, default=ObservedState.UNKNOWN
    )
    observed_state_updated_at = models.DateTimeField('观测时间', null=True, blank=True)
    observed_state_is_stale = models.BooleanField('观测数据已过期', default=True)
    operation_status = models.CharField('任务状态', max_length=16, default='PENDING')
    current_task = models.ForeignKey(
        'tasks.Task', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='当前任务'
    )

    last_error_code = models.CharField('最近错误码', max_length=64, blank=True, default='')
    last_error_message = models.TextField('最近错误信息', blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='instances',
        verbose_name='创建者',
    )
    disks_deleted = models.BooleanField('磁盘已清理', default=False)
    is_deleted = models.BooleanField('已注销', default=False)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '虚拟机实例'
        verbose_name_plural = '虚拟机实例'
        ordering = ['-created_at']
        permissions = [
            ('start_instance', '可以启动虚拟机'),
            ('shutdown_instance', '可以关闭虚拟机'),
            ('reboot_instance', '可以重启虚拟机'),
            ('force_stop_instance', '可以强制停止虚拟机'),
            ('delete_disk_instance', '可以在删除实例时删除磁盘'),
        ]
        indexes = [
            models.Index(fields=['node', 'observed_state']),
            models.Index(fields=['created_by', 'is_deleted']),
            models.Index(fields=['operation_status']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['node', 'libvirt_domain_name'], name='uniq_domain_name_per_node'
            ),
            models.UniqueConstraint(
                fields=['node', 'name'],
                condition=models.Q(is_deleted=False),
                name='uniq_instance_name_per_node',
            ),
        ]

    def __str__(self) -> str:
        """返回可读标识。"""
        return f'{self.name} ({self.observed_state})'

    @property
    def is_running(self) -> bool:
        """观测状态是否为运行中。"""
        return self.observed_state == ObservedState.RUNNING

    def mark_observed(self, state: str, now=None) -> None:
        """更新观测状态与时间，清除过期标记。

        Args:
            state: 归一化后的观测状态。
            now: 观测时间，默认当前时间。
        """
        self.observed_state = state
        self.observed_state_updated_at = now or timezone.now()
        self.observed_state_is_stale = False


class Disk(models.Model):
    """实例虚拟磁盘。"""

    instance = models.ForeignKey(
        Instance, on_delete=models.CASCADE, related_name='disks', verbose_name='实例'
    )
    role = models.CharField(
        '角色', max_length=16, choices=DiskRole.choices, default=DiskRole.SYSTEM
    )
    name = models.CharField('文件名', max_length=128)
    relative_path = models.CharField('相对路径', max_length=255, unique=True)
    format = models.CharField('格式', max_length=16, default='qcow2')
    size_gib = models.PositiveIntegerField('容量(GiB)')
    virtual_size_bytes = models.BigIntegerField('虚拟容量(字节)', null=True, blank=True)
    actual_size_bytes = models.BigIntegerField('实际占用(字节)', null=True, blank=True)
    bus = models.CharField('总线', max_length=16, default='virtio')
    target_dev = models.CharField('设备名', max_length=16, default='vda')
    status = models.CharField(
        '状态', max_length=16, choices=DiskStatus.choices, default=DiskStatus.CREATING
    )
    is_orphan = models.BooleanField('孤儿文件', default=False)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '虚拟磁盘'
        verbose_name_plural = '虚拟磁盘'
        indexes = [models.Index(fields=['instance', 'role'])]

    def __str__(self) -> str:
        """返回可读标识。"""
        return f'{self.instance_id}:{self.name} ({self.status})'


class ResourceReservation(models.Model):
    """创建实例时的资源预留，防止并发超分。"""

    node = models.ForeignKey(
        'nodes.Node', on_delete=models.CASCADE, related_name='reservations', verbose_name='节点'
    )
    task = models.OneToOneField(
        'tasks.Task', on_delete=models.CASCADE, related_name='reservation', verbose_name='任务'
    )
    instance = models.ForeignKey(
        Instance,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reservations',
        verbose_name='实例',
    )
    vcpu_reserved = models.PositiveIntegerField('预留 vCPU', default=0)
    memory_reserved_mib = models.PositiveIntegerField('预留内存(MiB)', default=0)
    disk_reserved_bytes = models.BigIntegerField('预留存储(字节)', default=0)
    status = models.CharField(
        '状态', max_length=16, choices=ReservationStatus.choices, default=ReservationStatus.HELD
    )
    expires_at = models.DateTimeField('过期时间')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '资源预留'
        verbose_name_plural = '资源预留'
        indexes = [
            models.Index(fields=['node', 'status']),
            models.Index(fields=['expires_at', 'status']),
        ]

    def __str__(self) -> str:
        """返回可读标识。"""
        return f'{self.node_id} vcpu={self.vcpu_reserved} mem={self.memory_reserved_mib}'
