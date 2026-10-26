"""请求中间件：生成并透传 request_id。"""

import re
import uuid

from django.http import HttpRequest, HttpResponse

from common.logging import request_id_var

REQUEST_ID_HEADER = 'X-Request-ID'
# 仅接受安全字符，避免把外部输入原样回显到响应头与日志
REQUEST_ID_PATTERN = re.compile(r'^[A-Za-z0-9_-]{8,64}$')


class RequestIDMiddleware:
    """为每个请求生成 request_id，并写入日志上下文与响应头。"""

    def __init__(self, get_response):
        """保存下一层处理器。"""
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """处理请求并附加 request_id。

        Args:
            request: 进入的 HTTP 请求。

        Returns:
            带 X-Request-ID 响应头的响应。
        """
        request_id = self.resolve_request_id(request)
        token = request_id_var.set(request_id)
        request.request_id = request_id
        try:
            response = self.get_response(request)
        finally:
            request_id_var.reset(token)
        response[REQUEST_ID_HEADER] = request_id
        return response

    @staticmethod
    def resolve_request_id(request: HttpRequest) -> str:
        """确定本次请求使用的 request_id。

        优先复用调用方传入且格式合法的值，便于跨系统链路追踪；否则生成新的。

        Args:
            request: 进入的 HTTP 请求。

        Returns:
            合法的 request_id 字符串。
        """
        inbound = request.headers.get(REQUEST_ID_HEADER, '')
        if REQUEST_ID_PATTERN.match(inbound):
            return inbound
        return uuid.uuid4().hex
