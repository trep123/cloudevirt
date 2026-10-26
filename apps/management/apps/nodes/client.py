"""节点 Agent HTTP 客户端。

所有请求带共享令牌并设置超时；异常统一转换为平台错误码，
禁止把 Agent 返回的堆栈或敏感路径直接透传。
"""

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings

from common.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)


class AgentClient:
    """节点 Agent 客户端。"""

    def __init__(self, endpoint: str, token: str = '', timeout: int | None = None) -> None:
        """初始化客户端。

        Args:
            endpoint: Agent 地址，形如 http://host:port。
            token: 共享令牌，缺省取 settings.AGENT_SHARED_TOKEN。
            timeout: 超时秒数，缺省取 settings.AGENT_REQUEST_TIMEOUT_SECONDS。
        """
        self.endpoint = endpoint.rstrip('/')
        self.token = token or getattr(settings, 'AGENT_SHARED_TOKEN', '')
        self.timeout = timeout or getattr(settings, 'AGENT_REQUEST_TIMEOUT_SECONDS', 30)

    def get_json(self, path: str) -> Any:
        """请求 Agent 的 JSON 接口。

        Args:
            path: 以 / 开头的路径。

        Returns:
            反序列化后的响应内容。

        Raises:
            AppError: 超时、连接失败、非 2xx 或响应不是合法 JSON。
        """
        request = urllib.request.Request(
            f'{self.endpoint}{path}',
            headers={'Authorization': f'Bearer {self.token}'},
            method='GET',
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = response.read().decode('utf-8')
        except urllib.error.HTTPError as exc:
            raise AppError(
                ErrorCode.NODE_OFFLINE,
                '节点 Agent 返回异常状态',
                details={'status': exc.code},
            ) from exc
        except urllib.error.URLError as exc:
            raise AppError(ErrorCode.NODE_OFFLINE, '无法连接节点 Agent') from exc
        except TimeoutError as exc:
            raise AppError(ErrorCode.COMMAND_TIMEOUT, '调用节点 Agent 超时') from exc

        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            logger.warning('Agent 响应不是合法 JSON', extra={'path': path})
            raise AppError(ErrorCode.OPERATION_FAILED, '节点 Agent 响应格式错误') from exc

    def health(self) -> dict:
        """读取健康检查。"""
        return self.get_json('/health')

    def resources(self) -> dict:
        """读取资源采集结果。"""
        return self.get_json('/api/v1/node/resources')

    def domains(self) -> list[dict]:
        """读取域列表。"""
        payload = self.get_json('/api/v1/domains')
        domains = payload.get('domains', []) if isinstance(payload, dict) else []
        return [item for item in domains if isinstance(item, dict)]
