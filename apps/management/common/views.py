"""公共视图：健康检查。"""

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def health(request: HttpRequest) -> JsonResponse:
    """返回进程存活状态，供部署健康检查使用。

    Args:
        request: HTTP 请求，未使用。

    Returns:
        形如 {"status": "ok", "version": "x.y.z"} 的 JSON 响应（免认证）。
    """
    return JsonResponse({'status': 'ok', 'version': settings.APP_VERSION})
