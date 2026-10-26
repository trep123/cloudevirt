"""公共视图：健康检查与 JSON 错误页。"""

from typing import Any

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET

from common.errors import ErrorCode, build_error_payload
from common.logging import get_request_id


def json_response(payload: dict[str, Any], status: int = 200) -> JsonResponse:
    """输出 UTF-8 未转义的 JSON 响应，统一全站编码行为。

    Args:
        payload: 待序列化的字典。
        status: HTTP 状态码。

    Returns:
        JsonResponse 对象。
    """
    return JsonResponse(payload, status=status, json_dumps_params={'ensure_ascii': False})


@require_GET
def health(request: HttpRequest) -> JsonResponse:
    """返回进程存活状态，供部署健康检查使用。

    Args:
        request: HTTP 请求，未使用。

    Returns:
        形如 {"status": "ok", "version": "x.y.z"} 的 JSON 响应（免认证）。
    """
    return json_response({'status': 'ok', 'version': settings.APP_VERSION})


def json_404(request: HttpRequest, exception: Exception) -> JsonResponse:
    """把未匹配路由的 404 统一为 JSON 错误结构。

    Args:
        request: HTTP 请求。
        exception: Django 抛出的解析异常。

    Returns:
        NOT_FOUND 结构的 JSON 响应，状态码 404。
    """
    payload = build_error_payload(ErrorCode.NOT_FOUND, '', {}, get_request_id())
    return json_response(payload, status=404)


def json_500(request: HttpRequest) -> JsonResponse:
    """把服务端错误统一为 JSON 错误结构，不泄露内部信息。

    Args:
        request: HTTP 请求。

    Returns:
        INTERNAL_ERROR 结构的 JSON 响应，状态码 500。
    """
    payload = build_error_payload(ErrorCode.INTERNAL_ERROR, '服务器内部错误', {}, get_request_id())
    return json_response(payload, status=500)
