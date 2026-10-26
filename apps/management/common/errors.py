"""统一错误码与业务异常定义。

对外只暴露稳定错误码与可读信息，禁止把内部堆栈、密钥或敏感路径返回给调用方。
错误响应统一结构见 common.exceptions.api_exception_handler。
"""

import logging

from django.db import models
from rest_framework import status

logger = logging.getLogger(__name__)


class ErrorCode(models.TextChoices):
    """平台统一错误码。"""

    UNAUTHORIZED = 'UNAUTHORIZED', '未认证或令牌无效'
    PERMISSION_DENIED = 'PERMISSION_DENIED', '已认证但没有操作权限'
    VALIDATION_ERROR = 'VALIDATION_ERROR', '请求参数不符合要求'
    INVALID_ARGUMENT = 'INVALID_ARGUMENT', '请求字段无效'
    NOT_FOUND = 'NOT_FOUND', '资源不存在'
    CONFLICT = 'CONFLICT', '资源状态不允许该操作'
    OPERATION_IN_PROGRESS = 'OPERATION_IN_PROGRESS', '该资源存在未结束的任务'
    INSUFFICIENT_RESOURCE = 'INSUFFICIENT_RESOURCE', '节点 CPU、内存或存储不足'
    IMAGE_IN_USE = 'IMAGE_IN_USE', '镜像被实例引用，禁止删除'
    NODE_OFFLINE = 'NODE_OFFLINE', '节点离线或维护中，不接受新任务'
    LIBVIRT_UNAVAILABLE = 'LIBVIRT_UNAVAILABLE', 'libvirt 服务不可用'
    COMMAND_TIMEOUT = 'COMMAND_TIMEOUT', '上游命令执行超时'
    RATE_LIMITED = 'RATE_LIMITED', '请求过于频繁'
    OPERATION_FAILED = 'OPERATION_FAILED', '操作失败'
    INTERNAL_ERROR = 'INTERNAL_ERROR', '服务器内部错误'


# 错误码到 HTTP 状态码的集中映射，禁止在各视图内硬编码状态码
ERROR_STATUS_MAP: dict[str, int] = {
    ErrorCode.UNAUTHORIZED: status.HTTP_401_UNAUTHORIZED,
    ErrorCode.PERMISSION_DENIED: status.HTTP_403_FORBIDDEN,
    ErrorCode.VALIDATION_ERROR: status.HTTP_400_BAD_REQUEST,
    ErrorCode.INVALID_ARGUMENT: status.HTTP_400_BAD_REQUEST,
    ErrorCode.NOT_FOUND: status.HTTP_404_NOT_FOUND,
    ErrorCode.CONFLICT: status.HTTP_409_CONFLICT,
    ErrorCode.OPERATION_IN_PROGRESS: status.HTTP_409_CONFLICT,
    ErrorCode.INSUFFICIENT_RESOURCE: status.HTTP_409_CONFLICT,
    ErrorCode.IMAGE_IN_USE: status.HTTP_409_CONFLICT,
    ErrorCode.NODE_OFFLINE: status.HTTP_503_SERVICE_UNAVAILABLE,
    ErrorCode.LIBVIRT_UNAVAILABLE: status.HTTP_503_SERVICE_UNAVAILABLE,
    ErrorCode.COMMAND_TIMEOUT: status.HTTP_504_GATEWAY_TIMEOUT,
    ErrorCode.RATE_LIMITED: status.HTTP_429_TOO_MANY_REQUESTS,
    ErrorCode.OPERATION_FAILED: status.HTTP_500_INTERNAL_SERVER_ERROR,
    ErrorCode.INTERNAL_ERROR: status.HTTP_500_INTERNAL_SERVER_ERROR,
}

# 未捕获异常对外展示的统一文案，避免泄露内部信息
INTERNAL_ERROR_MESSAGE = '服务器内部错误，请联系管理员并提供 request_id'


class AppError(Exception):
    """业务异常基类。

    Attributes:
        code: 稳定错误码，取自 ErrorCode。
        message: 面向调用方可读的错误信息。
        details: 字段级错误明细，如 {"memory_mib": ["必须大于 0"]}。
        status_code: HTTP 状态码，默认按 code 映射。
    """

    def __init__(
        self,
        code: str = ErrorCode.OPERATION_FAILED,
        message: str = '',
        details: dict | list | None = None,
        status_code: int | None = None,
    ) -> None:
        """初始化业务异常。

        Args:
            code: 错误码，默认 OPERATION_FAILED。
            message: 错误信息，留空时使用错误码默认文案。
            details: 字段级明细。
            status_code: 覆盖默认 HTTP 状态码。
        """
        self.code = code
        if message:
            self.message = message
        elif code in ErrorCode.values:
            self.message = str(ErrorCode(code).label)
        else:
            self.message = str(ErrorCode.OPERATION_FAILED.label)
        self.details = details if details is not None else {}
        self.status_code = status_code or ERROR_STATUS_MAP.get(
            code, status.HTTP_500_INTERNAL_SERVER_ERROR
        )
        super().__init__(self.message)


def build_error_payload(
    code: str,
    message: str,
    details: dict | list | None,
    request_id: str,
) -> dict:
    """构造统一错误响应体。

    Args:
        code: 错误码。
        message: 错误信息。
        details: 字段级明细。
        request_id: 链路追踪 ID。

    Returns:
        形如 {"error": {"code", "message", "details", "request_id"}} 的字典。
    """
    return {
        'error': {
            'code': code,
            'message': message or str(ErrorCode(code).label),
            'details': details if details is not None else {},
            'request_id': request_id,
        }
    }
