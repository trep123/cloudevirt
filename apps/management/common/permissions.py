"""权限判定统一入口。

所有写操作必须先经过本模块的判定：未认证抛 UNAUTHORIZED(401)，无权限抛
PERMISSION_DENIED(403) 并写入审计。前端隐藏按钮不作为权限边界。
"""

from rest_framework.permissions import BasePermission

from apps.audit.models import AuditAction
from apps.audit.services import record_denied
from common.errors import AppError, ErrorCode


def check_permission(
    user,
    codename: str,
    *,
    target_type: str = '',
    target_id: str = '',
    action: str = AuditAction.PERMISSION_DENIED,
) -> None:
    """校验用户是否具备指定权限，不满足时抛异常并审计。

    Args:
        user: 当前用户（取自会话/Token，不得使用客户端提交的身份字段）。
        codename: 权限码，形如 nodes.add_node。
        target_type: 操作对象类型，用于审计。
        target_id: 操作对象标识，用于审计。
        action: 审计动作，默认 PERMISSION_DENIED。

    Raises:
        AppError: 未认证（401）或无权限（403）。
    """
    if not user or not user.is_authenticated:
        raise AppError(ErrorCode.UNAUTHORIZED)
    if user.has_perm(codename):
        return
    record_denied(
        action=action,
        actor=user,
        target_type=target_type,
        target_id=target_id,
        codename=codename,
    )
    raise AppError(ErrorCode.PERMISSION_DENIED)


class RequiresPermission(BasePermission):
    """DRF 权限类：按权限码校验，未通过时由统一异常处理器转换响应。

    子类需指定 codename，可选覆盖 target_type / audit_action。
    """

    codename: str = ''
    target_type: str = ''
    audit_action: str = AuditAction.PERMISSION_DENIED

    def has_permission(self, request, view) -> bool:
        """执行权限校验，失败时抛出异常而非返回 False。

        Args:
            request: DRF 请求。
            view: 当前视图。

        Returns:
            校验通过返回 True。
        """
        check_permission(
            request.user,
            self.codename,
            target_type=self.target_type,
            action=self.audit_action,
        )
        return True


class CanManageUser(RequiresPermission):
    """用户与角色管理权限。"""

    codename = 'accounts.manage_user'
    target_type = 'user'


class RequiresPasswordChange(BasePermission):
    """强制修改初始口令：置位用户只能访问认证相关接口。

    各业务视图需显式加入该权限类，避免初始口令长期可用。
    """

    def has_permission(self, request, view) -> bool:
        """校验用户是否仍在使用初始口令。

        Returns:
            未置位或缺少档案时返回 True；置位时抛出 403。
        """
        user = request.user
        if not user or not user.is_authenticated:
            return True
        profile = getattr(user, 'profile', None)
        if profile is not None and profile.must_change_password:
            raise AppError(ErrorCode.PERMISSION_DENIED, '请先修改初始密码')
        return True


class CanOperateNode(RequiresPermission):
    """查看节点与资源的权限。"""

    codename = 'nodes.view_node'
    target_type = 'node'


class CanManageNode(RequiresPermission):
    """维护节点与节点授权的权限。"""

    codename = 'nodes.add_node'
    target_type = 'node'


class CanRegisterNode(RequiresPermission):
    """注册/变更/注销节点的权限。"""

    codename = 'nodes.add_node'
    target_type = 'node'


class CanRefreshNode(RequiresPermission):
    """主动刷新节点资源的权限。"""

    codename = 'nodes.refresh_node'
    target_type = 'node'


class CanViewTask(RequiresPermission):
    """查看任务的权限。"""

    codename = 'tasks.view_task'
    target_type = 'task'


class CanCancelTask(RequiresPermission):
    """取消任务的权限。"""

    codename = 'tasks.cancel_task'
    target_type = 'task'


class CanRetryTask(RequiresPermission):
    """重试任务的权限。"""

    codename = 'tasks.retry_task'
    target_type = 'task'


class CanViewImage(RequiresPermission):
    """查看镜像的权限。"""

    codename = 'images.view_image'
    target_type = 'image'


class CanImportImage(RequiresPermission):
    """导入镜像的权限。"""

    codename = 'images.add_image'
    target_type = 'image'


class CanDeleteImage(RequiresPermission):
    """删除镜像的权限。"""

    codename = 'images.delete_image'
    target_type = 'image'


class CanViewInstance(RequiresPermission):
    """查看实例的权限。"""

    codename = 'instances.view_instance'
    target_type = 'instance'


class CanCreateInstance(RequiresPermission):
    """创建实例的权限。"""

    codename = 'instances.add_instance'
    target_type = 'instance'


class CanViewNetwork(RequiresPermission):
    """查看网络的权限。"""

    codename = 'networks.view_network'
    target_type = 'network'


class CanManageNetwork(RequiresPermission):
    """维护网络白名单的权限。"""

    codename = 'networks.manage_network'
    target_type = 'network'


class CanViewMonitoring(RequiresPermission):
    """查看监控、告警与对账结果的权限。"""

    codename = 'monitoring.view_alert'
    target_type = 'monitoring'


class CanRunReconciliation(RequiresPermission):
    """手动触发对账的权限。"""

    codename = 'monitoring.run_reconciliation'
    target_type = 'monitoring'


class CanViewTemplate(RequiresPermission):
    """查看模板的权限。"""

    codename = 'templates.view_template'
    target_type = 'template'


class CanManageTemplate(RequiresPermission):
    """维护模板的权限。"""

    codename = 'templates.add_template'
    target_type = 'template'
