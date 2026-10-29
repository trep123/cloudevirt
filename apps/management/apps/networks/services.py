"""网络白名单校验。"""

from apps.networks.models import Network
from common.errors import AppError, ErrorCode


def validate_network_for_instance(name: str, node=None) -> Network | None:
    """校验实例要接入的网络是否在白名单内且可用。

    Args:
        name: 网络名称，空字符串表示不接入网络。

    Returns:
        命中的网络对象；名称为空时返回 None。

    Raises:
        AppError: 网络不在白名单、被标记为管理网或已删除。
    """
    if not name:
        return None
    network = Network.objects.filter(name=name, is_deleted=False).first()
    if network is None:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            '网络不在白名单内',
            details={'network_name': ['请先在网络白名单中登记该网络']},
        )
    if not network.is_usable:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            '不允许接入管理网络或尚未成功创建的网桥',
            details={'network_name': ['该网络被标记为管理网']},
        )
    if node is not None and network.node_id and network.node_id != node.pk:
        raise AppError(ErrorCode.CONFLICT, '网络网桥位于其他节点')
    return network


def default_network_name() -> str:
    """返回默认网络名称，未配置时返回空串。"""
    network = Network.objects.filter(is_default=True, is_deleted=False).first()
    return network.name if network else ''
