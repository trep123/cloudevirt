"""审计事件模型与动作字典。

审计是安全边界的一部分：登录、权限被拒、用户管理、危险操作都必须留痕。
"""

from django.conf import settings
from django.db import models


class AuditResult(models.TextChoices):
    """审计结果。"""

    SUCCESS = 'SUCCESS', '成功'
    FAILURE = 'FAILURE', '失败'
    DENIED = 'DENIED', '被拒绝'


class AuditAction(models.TextChoices):
    """审计动作，后续模块按需扩展。"""

    LOGIN_SUCCESS = 'LOGIN_SUCCESS', '登录成功'
    LOGIN_FAILURE = 'LOGIN_FAILURE', '登录失败'
    LOGOUT = 'LOGOUT', '登出'
    PASSWORD_CHANGE = 'PASSWORD_CHANGE', '修改密码'
    PERMISSION_DENIED = 'PERMISSION_DENIED', '权限被拒'
    USER_CREATE = 'USER_CREATE', '创建用户'
    USER_UPDATE = 'USER_UPDATE', '更新用户'
    USER_DISABLE = 'USER_DISABLE', '禁用用户'
    USER_ENABLE = 'USER_ENABLE', '启用用户'
    USER_DELETE = 'USER_DELETE', '删除用户'
    USER_PASSWORD_RESET = 'USER_PASSWORD_RESET', '重置用户密码'
    ROLE_CHANGE = 'ROLE_CHANGE', '变更角色'
    NODE_REGISTER = 'NODE_REGISTER', '注册节点'
    NODE_UPDATE = 'NODE_UPDATE', '更新节点'
    NODE_REFRESH = 'NODE_REFRESH', '刷新节点资源'
    NODE_OFFLINE = 'NODE_OFFLINE', '节点离线'
    IMAGE_IMPORT = 'IMAGE_IMPORT', '导入镜像'
    IMAGE_DELETE = 'IMAGE_DELETE', '删除镜像'
    INSTANCE_CREATE = 'INSTANCE_CREATE', '创建实例'
    INSTANCE_START = 'INSTANCE_START', '启动实例'
    INSTANCE_SHUTDOWN = 'INSTANCE_SHUTDOWN', '关闭实例'
    INSTANCE_FORCE_STOP = 'INSTANCE_FORCE_STOP', '强制停止实例'
    INSTANCE_REBOOT = 'INSTANCE_REBOOT', '重启实例'
    INSTANCE_DELETE = 'INSTANCE_DELETE', '删除实例'
    NETWORK_CREATE = 'NETWORK_CREATE', '登记网络'
    NETWORK_UPDATE = 'NETWORK_UPDATE', '更新网络'
    NETWORK_DELETE = 'NETWORK_DELETE', '删除网络'
    RECONCILE_RUN = 'RECONCILE_RUN', '执行对账'
    TEMPLATE_CREATE = 'TEMPLATE_CREATE', '创建模板'
    TEMPLATE_UPDATE = 'TEMPLATE_UPDATE', '更新模板'
    TEMPLATE_DELETE = 'TEMPLATE_DELETE', '删除模板'


class AuditEvent(models.Model):
    """审计事件记录，只追加不修改。"""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_events',
        verbose_name='操作者',
    )
    actor_username = models.CharField('操作者账号', max_length=150, blank=True, default='')
    action = models.CharField('动作', max_length=64, choices=AuditAction.choices)
    target_type = models.CharField('对象类型', max_length=32, blank=True, default='')
    target_id = models.CharField('对象标识', max_length=64, blank=True, default='')
    result = models.CharField(
        '结果', max_length=16, choices=AuditResult.choices, default=AuditResult.SUCCESS
    )
    request_id = models.CharField('请求 ID', max_length=64, blank=True, default='')
    task_id = models.UUIDField('任务 ID', null=True, blank=True)
    ip = models.GenericIPAddressField('来源 IP', null=True, blank=True)
    details = models.JSONField('详情', default=dict, blank=True)
    created_at = models.DateTimeField('发生时间', auto_now_add=True)

    class Meta:
        verbose_name = '审计事件'
        verbose_name_plural = '审计事件'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['target_type', 'target_id', 'created_at']),
            models.Index(fields=['actor', 'created_at']),
            models.Index(fields=['action', 'created_at']),
        ]

    def __str__(self) -> str:
        """返回可读摘要。"""
        return (
            f'{self.actor_username} {self.action} {self.target_type}:{self.target_id} {self.result}'
        )
