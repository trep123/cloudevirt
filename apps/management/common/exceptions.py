"""DRF 统一异常处理器。

把业务异常、DRF 异常与未捕获异常统一转换为：
{"error": {"code", "message", "details", "request_id"}}
"""

import logging

from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    NotAuthenticated,
    PermissionDenied,
    ValidationError,
)
from rest_framework.response import Response

from common.errors import (
    INTERNAL_ERROR_MESSAGE,
    AppError,
    ErrorCode,
    build_error_payload,
)
from common.logging import get_request_id

logger = logging.getLogger(__name__)

# DRF 内置异常到平台错误码的映射
DRF_ERROR_MAP: dict[type, str] = {
    NotAuthenticated: ErrorCode.UNAUTHORIZED,
    PermissionDenied: ErrorCode.PERMISSION_DENIED,
    ValidationError: ErrorCode.VALIDATION_ERROR,
}


def api_exception_handler(exc: Exception, context: dict) -> Response | None:
    """统一异常转换入口，配置在 REST_FRAMEWORK.EXCEPTION_HANDLER。

    Args:
        exc: 捕获到的异常。
        context: DRF 提供的上下文，包含 view、request 等。

    Returns:
        统一结构的错误响应；未处理时回退到 DRF 默认处理。
    """
    request_id = get_request_id()

    if isinstance(exc, AppError):
        return _error_response(exc.code, exc.message, exc.details, request_id, exc.status_code)

    if isinstance(exc, Http404):
        return _error_response(ErrorCode.NOT_FOUND, None, {}, request_id)

    if isinstance(exc, NotAuthenticated):
        return _error_response(ErrorCode.UNAUTHORIZED, None, {}, request_id)

    if isinstance(exc, PermissionDenied):
        return _error_response(ErrorCode.PERMISSION_DENIED, None, {}, request_id)

    if isinstance(exc, ValidationError):
        return _error_response(ErrorCode.VALIDATION_ERROR, None, exc.detail, request_id)

    if isinstance(exc, APIException):
        code = DRF_ERROR_MAP.get(type(exc), ErrorCode.OPERATION_FAILED)
        return _error_response(code, None, getattr(exc, 'detail', {}), request_id, exc.status_code)

    # 未捕获异常：记录完整堆栈到日志，对外只返回通用文案
    logger.exception('未处理异常', exc_info=exc)
    return _error_response(ErrorCode.INTERNAL_ERROR, INTERNAL_ERROR_MESSAGE, {}, request_id)


def _error_response(
    code: str,
    message: str | None,
    details,
    request_id: str,
    status_code: int | None = None,
) -> Response:
    """构造统一错误响应。

    Args:
        code: 平台错误码。
        message: 错误信息，为空时使用错误码默认文案。
        details: 字段级明细。
        request_id: 链路追踪 ID。
        status_code: 覆盖默认 HTTP 状态码。

    Returns:
        DRF 响应对象。
    """
    from common.errors import ERROR_STATUS_MAP

    payload = build_error_payload(code, message or '', details, request_id)
    http_status = status_code or ERROR_STATUS_MAP.get(code, status.HTTP_500_INTERNAL_SERVER_ERROR)
    return Response(payload, status=http_status)
