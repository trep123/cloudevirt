"""�ڵ� Agent HTTP �ͻ��ˡ�

����������������Ʋ����ó�ʱ���쳣ͳһת��Ϊƽ̨�����룬
��ֹ�� Agent ���صĶ�ջ������·��ֱ��͸����
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
            '�ڵ� Agent ��֤ʧ�ܣ���������˺ͽڵ㹲����������',
        )
    elif code not in ErrorCode.values:
        code, message = ErrorCode.OPERATION_FAILED, '�ڵ� Agent �����쳣��Ӧ������ڵ���־�Ͱ汾'
    if not message:
        message = '�ڵ� Agent ִ��ʧ�ܣ�����ڵ���־'
    return AppError(
        code, message, details={'agent_status': exc.code, 'agent_request_id': request_id}
    )


class AgentClient:
    """�ڵ� Agent �ͻ��ˡ�"""

    def __init__(self, endpoint: str, token: str = '', timeout: int | None = None) -> None:
        """��ʼ���ͻ��ˡ�

        Args:
            endpoint: Agent ��ַ������ http://host:port��
            token: �������ƣ�ȱʡȡ settings.AGENT_SHARED_TOKEN��
            timeout: ��ʱ������ȱʡȡ settings.AGENT_REQUEST_TIMEOUT_SECONDS��
        """
        self.endpoint = endpoint.rstrip('/')
        self.token = token or getattr(settings, 'AGENT_SHARED_TOKEN', '')
        self.timeout = timeout or getattr(settings, 'AGENT_REQUEST_TIMEOUT_SECONDS', 30)

    def get_json(self, path: str) -> Any:
        """���� Agent �� JSON �ӿڡ�

        Args:
            path: �� / ��ͷ��·����

        Returns:
            �����л������Ӧ���ݡ�

        Raises:
            AppError: ��ʱ������ʧ�ܡ��� 2xx ����Ӧ���ǺϷ� JSON��
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
            raise AppError(ErrorCode.NODE_OFFLINE, '�޷����ӽڵ� Agent') from exc
        except TimeoutError as exc:
            raise AppError(ErrorCode.COMMAND_TIMEOUT, '���ýڵ� Agent ��ʱ') from exc

        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            logger.warning('Agent ��Ӧ���ǺϷ� JSON', extra={'path': path})
            raise AppError(ErrorCode.OPERATION_FAILED, '�ڵ� Agent ��Ӧ��ʽ����') from exc

    def health(self) -> dict:
        """��ȡ������顣"""
        return self.get_json('/health')

    def resources(self) -> dict:
        """��ȡ��Դ�ɼ������"""
        return self.get_json('/api/v1/node/resources')

    def request_json(
        self, path: str, method: str, body: dict | None = None, *, timeout: int | None = None
    ) -> Any:
        """���ʹ� JSON �����������д��������"""
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
            raise AppError(ErrorCode.NODE_OFFLINE, '�޷����ӽڵ� Agent') from exc
        except TimeoutError as exc:
            raise AppError(ErrorCode.COMMAND_TIMEOUT, '���ýڵ� Agent ��ʱ') from exc
        try:
            return json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise AppError(ErrorCode.OPERATION_FAILED, '�ڵ� Agent ��Ӧ��ʽ����') from exc

    def upload_chunk(self, upload_id: str, offset: int, size: int, extension: str, data: bytes):
        query = f'?offset={offset}&size={size}&extension={extension}'
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
                ErrorCode.NODE_OFFLINE, '�޷����ӽڵ� Agent���ϴ�����ͣ���ɲ�ѯ���Ⱥ����'
            ) from exc
        except TimeoutError as exc:
            raise AppError(
                ErrorCode.COMMAND_TIMEOUT, '��Ƭ��Ӧ��ʱ�����ѯ�ѽ��ս��Ⱥ����'
            ) from exc

    def inspect_image(self, relative_path: str) -> dict:
        """���� Agent ��龵���ļ�����ʽ��������У��ͣ���"""
        return self.request_json('/api/v1/images/inspect', 'POST', {'relative_path': relative_path})

    def delete_image(self, relative_path: str) -> dict:
        """���� Agent ɾ�������ļ������������ƻ��Կ���Լ������"""
        return self.request_json('/api/v1/images', 'DELETE', {'relative_path': relative_path})

    def create_domain(self, payload: dict) -> dict:
        """���� Agent ������������"""
        return self.request_json('/api/v1/domains', 'POST', payload, timeout=590)

    def domain_display(self, name, config=None):
        path = f'/api/v1/domains/{quote(name, safe="")}/display'
        return self.get_json(path) if config is None else self.request_json(path, 'POST', config)

    def domain_addresses(self, name: str) -> dict:
        """��ȡ���������� IPv4/IPv6 ��ַ��"""
        return self.get_json(f'/api/v1/domains/{quote(name, safe="")}/addresses')

    def domain_interfaces(self, name: str) -> dict:
        """��ȡ�������ӿ���Ϣ��"""
        return self.get_json(f'/api/v1/domains/{quote(name, safe="")}/interfaces')

    def domain_action(self, name: str, action: str) -> dict:
        """ִ���������start / shutdown / force-stop / reboot��"""
        return self.request_json(f'/api/v1/domains/{name}/{action}', 'POST', {})

    def delete_domain(self, name: str, disk_relative_path: str = '') -> dict:
        """ɾ�����壬��ѡɾ�������ļ���"""
        suffix = f'?disk_relative_path={disk_relative_path}' if disk_relative_path else ''
        return self.request_json(f'/api/v1/domains/{name}{suffix}', 'DELETE')

    def list_disks(self) -> list[dict]:
        """�г��ڵ����Ŀ¼�е��ļ���"""
        payload = self.get_json('/api/v1/disks')
        # ͬ�ϣ���Ŀ¼ʱ Agent ���ܷ��� null
        disks = (payload.get('disks') or []) if isinstance(payload, dict) else []
        return [item for item in disks if isinstance(item, dict)]

    def delete_domain_disks(self, name, paths):
        from urllib.parse import urlencode

        return self.request_json(
            '/api/v1/domains/' + name + '?' + urlencode({'disk_relative_path': paths}, doseq=True),
            'DELETE',
        )

    def domains(self) -> list[dict]:
        """��ȡ���б���"""
        payload = self.get_json('/api/v1/domains')
        # Agent ������ʱ�᷵�� null��Go nil slice����ͳһ�����б�����
        domains = (payload.get('domains') or []) if isinstance(payload, dict) else []
        return [item for item in domains if isinstance(item, dict)]
