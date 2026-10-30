"""节点 Agent HTTP 客户端。

所有请求带共享令牌并设置超时；异常统一转换为平台错误码，
禁止把 Agent 返回的堆栈或敏感路径直接透传。
"""

import json
import logging
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import quote

from django.conf import settings

from common.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)


def agent_http_error(exc):
    """Preserve the Agent's public error, never return raw HTML or authentication status."""
    try:
        payload = json.loads(exc.read(8192).decode('utf-8'))
        detail = payload.get('error', payload)
        code = detail.get('code', '')
        message = str(detail.get('message', ''))[:500]
        request_id = str(detail.get('request_id', ''))[:128]
    except ValueError, AttributeError, TypeError:
        code, message, request_id = '', '', ''
    if code == 'UNAUTHORIZED' or exc.code in {401, 403}:
        code, message = (
            ErrorCode.OPERATION_FAILED,
            '节点 Agent 认证失败，请检查管理端和节点共享令牌配置',
        )
    elif code not in ErrorCode.values:
        code, message = ErrorCode.OPERATION_FAILED, '节点 Agent 返回异常响应，请检查节点日志和版本'
    if not message:
        message = '节点 Agent 执行失败，请检查节点日志'
    return AppError(
        code, message, details={'agent_status': exc.code, 'agent_request_id': request_id}
    )


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
            raise agent_http_error(exc) from exc
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

    def request_json(
        self, path: str, method: str, body: dict | None = None, *, timeout: int | None = None
    ) -> Any:
        """发送带 JSON 体的请求（用于写操作）。"""
        payload = (
            json.dumps(body or {}, ensure_ascii=False).encode('utf-8') if body is not None else None
        )
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
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                raw = response.read().decode('utf-8')
        except urllib.error.HTTPError as exc:
            raise agent_http_error(exc) from exc
        except urllib.error.URLError as exc:
            raise AppError(ErrorCode.NODE_OFFLINE, '无法连接节点 Agent') from exc
        except TimeoutError as exc:
            raise AppError(ErrorCode.COMMAND_TIMEOUT, '调用节点 Agent 超时') from exc
        try:
            return json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise AppError(ErrorCode.OPERATION_FAILED, '节点 Agent 响应格式错误') from exc

    def upload_chunk(
        self, upload_id: str, offset: int, size: int, extension: str, data: bytes, storage_pool=''
    ):
        query = f'?offset={offset}&size={size}&extension={extension}'
        if storage_pool:
            query += '&storage_pool=' + quote(storage_pool, safe='')
        request = urllib.request.Request(
            f'{self.endpoint}/api/v1/images/uploads/{upload_id}{query}',
            data=data,
            method='PUT',
            headers={
                'Authorization': f'Bearer {self.token}',
                'Content-Type': 'application/octet-stream',
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            raise agent_http_error(exc) from exc
        except urllib.error.URLError as exc:
            raise AppError(
                ErrorCode.NODE_OFFLINE, '无法连接节点 Agent，上传已暂停，可查询进度后继续'
            ) from exc
        except TimeoutError as exc:
            raise AppError(
                ErrorCode.COMMAND_TIMEOUT, '分片响应超时，请查询已接收进度后继续'
            ) from exc

    def inspect_image(self, relative_path: str, storage_pool='') -> dict:
        """请求 Agent 检查镜像文件（格式、容量、校验和）。"""
        return self.request_json(
            '/api/v1/images/inspect',
            'POST',
            {
                'relative_path': relative_path,
                **({'storage_pool': storage_pool} if storage_pool else {}),
            },
        )

    def delete_image(self, relative_path: str, storage_pool='') -> dict:
        """请求 Agent 删除镜像文件（受宿主机破坏性开关约束）。"""
        return self.request_json(
            '/api/v1/images',
            'DELETE',
            {
                'relative_path': relative_path,
                **({'storage_pool': storage_pool} if storage_pool else {}),
            },
        )

    def create_domain(self, payload: dict) -> dict:
        """请求 Agent 创建并启动域。"""
        return self.request_json('/api/v1/domains', 'POST', payload, timeout=590)

    def domain_display(self, name, config=None):
        path = f'/api/v1/domains/{quote(name, safe="")}/display'
        return self.get_json(path) if config is None else self.request_json(path, 'POST', config)

    def domain_hardware(self, name, payload=None, *, storage_pool=''):
        path = f'/api/v1/domains/{quote(name, safe="")}/hardware'
        if storage_pool:
            path += f'?storage_pool={quote(storage_pool, safe="")}'
        return (
            self.get_json(path)
            if payload is None
            else self.request_json(path, 'POST', payload, timeout=90)
        )

    def domain_addresses(self, name: str) -> dict:
        """读取域内网卡的 IPv4/IPv6 地址。"""
        return self.get_json(f'/api/v1/domains/{quote(name, safe="")}/addresses')

    def domain_interfaces(self, name: str) -> dict:
        """读取域网卡接口信息。"""
        return self.get_json(f'/api/v1/domains/{quote(name, safe="")}/interfaces')

    def domain_action(self, name: str, action: str) -> dict:
        """执行域操作：start / shutdown / force-stop / reboot。"""
        return self.request_json(f'/api/v1/domains/{name}/{action}', 'POST', {})

    def delete_domain(
        self, name: str, disk_relative_path: str = '', *, storage_pool: str = ''
    ) -> dict:
        """删除域定义，可选删除磁盘文件。"""
        from urllib.parse import urlencode

        query = {}
        if disk_relative_path:
            query['disk_relative_path'] = disk_relative_path
        if storage_pool:
            query['storage_pool'] = storage_pool
        suffix = '?' + urlencode(query) if query else ''
        return self.request_json(f'/api/v1/domains/{quote(name, safe="")}{suffix}', 'DELETE')

    def list_disks(self) -> list[dict]:
        """列出节点磁盘目录中的文件。"""
        payload = self.get_json('/api/v1/disks')
        # 同上：空目录时 Agent 可能返回 null
        disks = (payload.get('disks') or []) if isinstance(payload, dict) else []
        return [item for item in disks if isinstance(item, dict)]

    def delete_domain_disks(self, name, paths, *, storage_pool=''):
        from urllib.parse import urlencode

        query = {'disk_relative_path': paths}
        if storage_pool:
            query['storage_pool'] = storage_pool
        return self.request_json(
            '/api/v1/domains/' + quote(name, safe='') + '?' + urlencode(query, doseq=True),
            'DELETE',
        )

    def domains(self) -> list[dict]:
        """读取域列表。"""
        payload = self.get_json('/api/v1/domains')
        # Agent 在无域时会返回 null（Go nil slice），统一按空列表处理
        domains = (payload.get('domains') or []) if isinstance(payload, dict) else []
        return [item for item in domains if isinstance(item, dict)]
