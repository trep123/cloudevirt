"""测试替身：模拟节点 Agent 客户端。"""

from common.errors import AppError


class FakeAgentClient:
    """可配置成功/失败的 Agent 客户端替身。"""

    def __init__(self, resources=None, error=None) -> None:
        """初始化替身。

        Args:
            resources: 采集成功时返回的资源字典。
            error: 抛出业务异常时使用的错误码，设置后所有调用均失败。
        """
        self._resources = resources or {
            'cpu_logical': 16,
            'memory_total_mib': 32768,
            'memory_available_mib': 16384,
            'storage': [
                {'path': '/var/lib/cloudvirt', 'total_bytes': 1000, 'free_bytes': 400},
                {'path': '/var/lib/cloudvirt/disks', 'total_bytes': 2000, 'free_bytes': 500},
            ],
        }
        self.error = error
        self.calls: list[str] = []

    def health(self) -> dict:
        """返回健康检查；配置错误码时抛出异常。"""
        self.calls.append('health')
        self._raise_if_needed()
        return {'status': 'ok', 'version': '0.1.0'}

    def resources(self) -> dict:
        """返回资源采集结果；配置错误码时抛出异常。"""
        self.calls.append('resources')
        self._raise_if_needed()
        return self._resources

    def domains(self) -> list[dict]:
        """返回域列表；配置错误码时抛出异常。"""
        self.calls.append('domains')
        self._raise_if_needed()
        return [{'name': 'vm-1', 'state': 'RUNNING'}]

    def _raise_if_needed(self) -> None:
        """按配置抛出业务异常。"""
        if self.error:
            raise AppError(self.error, '模拟采集失败')
