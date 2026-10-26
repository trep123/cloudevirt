"""用户扩展档案。

认证主体复用 django.contrib.auth 的 User，角色复用 Group + Permission（ADR-006），
本模型只承载登录安全与展示相关的扩展字段。
"""

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
