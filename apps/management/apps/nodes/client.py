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

    def request_json(self, path: str, method: str, body: dict | None = None) -> Any:
        """发送带 JSON 体的请求（用于写操作）。"""
        payload = json.dumps(body or {}).encode('utf-8') if body is not None else None
        request = urllib.request.Request(
            f'{self.endpoint}{path}',
            data=payload,
            headers={
                'Authorization': f'Bearer {self.token}',
                'Content-Type': 'application/json',
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode('utf-8')
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode('utf-8', errors='ignore')[:200]
            raise AppError(
                ErrorCode.OPERATION_FAILED,
                '节点 Agent 拒绝了该操作',
                details={'status': exc.code, 'response': detail},
            ) from exc
        except urllib.error.URLError as exc:
            raise AppError(ErrorCode.NODE_OFFLINE, '无法连接节点 Agent') from exc
        except TimeoutError as exc:
            raise AppError(ErrorCode.COMMAND_TIMEOUT, '调用节点 Agent 超时') from exc
        return json.loads(raw) if raw else {}

    def inspect_image(self, relative_path: str) -> dict:
        """请求 Agent 检查镜像文件（格式、容量、校验和）。"""
        return self.request_json('/api/v1/images/inspect', 'POST', {'relative_path': relative_path})

    def delete_image(self, relative_path: str) -> dict:
        """请求 Agent 删除镜像文件（受宿主机破坏性开关约束）。"""
        return self.request_json('/api/v1/images', 'DELETE', {'relative_path': relative_path})

    def create_domain(self, payload: dict) -> dict:
        """请求 Agent 创建并启动域。"""
        return self.request_json('/api/v1/domains', 'POST', payload)

    def domain_action(self, name: str, action: str) -> dict:
        """执行域操作：start / shutdown / force-stop / reboot。"""
        return self.request_json(f'/api/v1/domains/{name}/{action}', 'POST', {})

    def delete_domain(self, name: str, disk_relative_path: str = '') -> dict:
        """删除域定义，可选删除磁盘文件。"""
        suffix = f'?disk_relative_path={disk_relative_path}' if disk_relative_path else ''
        return self.request_json(f'/api/v1/domains/{name}{suffix}', 'DELETE')

    def list_disks(self) -> list[dict]:
        """列出节点磁盘目录中的文件。"""
        payload = self.get_json('/api/v1/disks')
        # 同上：空目录时 Agent 可能返回 null
        disks = (payload.get('disks') or []) if isinstance(payload, dict) else []
        return [item for item in disks if isinstance(item, dict)]

    def domains(self) -> list[dict]:
        """读取域列表。"""
        payload = self.get_json('/api/v1/domains')
        # Agent 在无域时会返回 null（Go nil slice），统一按空列表处理
        domains = (payload.get('domains') or []) if isinstance(payload, dict) else []
        return [item for item in domains if isinstance(item, dict)]
