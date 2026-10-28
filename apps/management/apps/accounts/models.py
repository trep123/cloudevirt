"""用户扩展档案。

认证主体复用 django.contrib.auth 的 User，角色复用 Group + Permission（ADR-006），
本模型只承载登录安全与展示相关的扩展字段。
"""

import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class UserProfile(models.Model):
    """用户扩展档案，与 User 一对一。"""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
        verbose_name='用户',
    )
    display_name = models.CharField('显示名', max_length=64)
    remark = models.CharField(max_length=500, blank=True, default='')
    quota_overrides = models.JSONField(default=dict, blank=True)
    node_scope = models.JSONField(null=True, blank=True, default=None)
    session_version = models.PositiveIntegerField(default=0)
    locale = models.CharField('界面语言', max_length=16, default='zh-CN')
    must_change_password = models.BooleanField('必须修改密码', default=False)
    password_changed_at = models.DateTimeField('密码修改时间', null=True, blank=True)
    failed_login_count = models.PositiveIntegerField('连续登录失败次数', default=0)
    locked_until = models.DateTimeField('锁定截止时间', null=True, blank=True)
    last_login_ip = models.GenericIPAddressField('最近登录 IP', null=True, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '用户档案'
        verbose_name_plural = '用户档案'
        permissions = [
            ('manage_user', '可以管理用户、角色与节点授权'),
            ('manage_settings', '可以修改系统设置'),
            ('view_audit', '可以查看审计日志'),
            ('manage_role', '可以管理自定义角色'),
            ('import_user', '可以批量导入用户'),
            ('export_user', '可以批量导出用户'),
            ('export_sensitive_user', '可以导出用户邮箱和备注'),
        ]

    def __str__(self) -> str:
        """返回可读标识。"""
        return f'{self.user.get_username()} ({self.display_name})'

    @property
    def is_locked(self) -> bool:
        """返回账号当前是否处于锁定状态。"""
        return bool(self.locked_until and self.locked_until > timezone.now())

    def register_failure(self, max_failed: int, lock_seconds: int) -> None:
        """记录一次登录失败，达到阈值后锁定账号。

        Args:
            max_failed: 允许的最大连续失败次数。
            lock_seconds: 锁定时长（秒）。
        """
        self.failed_login_count += 1
        if self.failed_login_count >= max_failed:
            self.locked_until = timezone.now() + timedelta(seconds=lock_seconds)
            self.failed_login_count = 0
        self.save(update_fields=['failed_login_count', 'locked_until', 'updated_at'])

    def register_success(self, ip: str | None = None) -> None:
        """登录成功：清零失败计数并记录来源 IP。

        Args:
            ip: 来源 IP。
        """
        self.failed_login_count = 0
        self.locked_until = None
        if ip:
            self.last_login_ip = ip
        self.save(
            update_fields=['failed_login_count', 'locked_until', 'last_login_ip', 'updated_at']
        )


class RoleDefinition(models.Model):
    group = models.OneToOneField('auth.Group', on_delete=models.CASCADE, related_name='definition')
    display_name = models.CharField(max_length=64)
    description = models.CharField(max_length=500, blank=True, default='')
    enabled = models.BooleanField(default=True)
    scope = models.CharField(
        max_length=16,
        default='owned',
        choices=[('owned', '本人资源'), ('nodes', '指定节点上的本人资源')],
    )
    nodes = models.ManyToManyField('nodes.Node', blank=True)
    permission_codes = models.JSONField(default=list)
    revision = models.PositiveIntegerField(default=1)

    def __str__(self):
        return self.group.name


class AccountBatch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    task = models.OneToOneField('tasks.Task', on_delete=models.PROTECT, null=True, blank=True)
    kind = models.CharField(max_length=10)
    format = models.CharField(max_length=5, default='csv')
    mode = models.CharField(max_length=10, default='create')
    strict = models.BooleanField(default=False)
    state = models.CharField(max_length=16, default='DRAFT')
    rows = models.JSONField(default=list)
    results = models.JSONField(default=list)
    options = models.JSONField(default=dict)
    file_data = models.BinaryField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    def __str__(self):
        return str(self.pk)
