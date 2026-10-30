"""节点心跳与资源采集服务。

规则：
- 采集成功更新采样值与采样时间；
- 采集失败保留上次有效值并标记过期，禁止把字段清零；
- 连续失败或超过离线阈值后置 OFFLINE，维护态不被自动改写。
"""

import logging
from datetime import timedelta

from django.utils import timezone

from apps.audit.models import AuditAction
from apps.audit.services import record_audit
from apps.nodes.client import AgentClient
from apps.nodes.models import Node, NodeStatus
from common.errors import AppError

logger = logging.getLogger(__name__)


def build_client(node: Node) -> AgentClient:
    """为节点创建 Agent 客户端。"""
    return AgentClient(node.endpoint, timeout=node.heartbeat_interval_seconds)


def refresh_node(node: Node, client: AgentClient | None = None) -> Node:
    """采集一次节点状态并回写数据库。

    Args:
        node: 目标节点。
        client: 客户端，缺省按节点配置创建（测试可注入）。

    Returns:
        更新后的节点对象。
    """
    agent = client or build_client(node)
    now = timezone.now()
    try:
        health = agent.health()
        resources = agent.resources()
    except AppError as exc:
        node.consecutive_failures += 1
        node.last_error_code = exc.code
        node.last_error_message = exc.message
        node.resource_is_stale = True
        changed = node.mark_offline_if_expired(now)
        node.save(
            update_fields=[
                'status',
                'consecutive_failures',
                'last_error_code',
                'last_error_message',
                'resource_is_stale',
                'updated_at',
            ]
        )
        logger.warning(
            '节点采集失败',
            extra={
                'node_id': node.pk,
                'error_code': exc.code,
                'consecutive_failures': node.consecutive_failures,
                'result': 'failure',
            },
        )
        if changed:
            record_audit(
                action=AuditAction.NODE_OFFLINE,
                target_type='node',
                target_id=str(node.pk),
                details={'name': node.name, 'reason': exc.code},
            )
        return node

    storage_total = 0
    storage_free = 0
    filesystems = {}
    for index, item in enumerate(resources.get('storage') or []):
        # New Agents identify the actual filesystem, preserving each path in the API.
        # Old Agents without identity retain their previous per-path accounting.
        key = (
            ('filesystem', str(item['filesystem_id']))
            if item.get('filesystem_id')
            else ('legacy', index)
        )
        total = int(item.get('total_bytes') or 0)
        free = int(item.get('free_bytes') or 0)
        if key in filesystems:
            previous_total, previous_free = filesystems[key]
            filesystems[key] = (min(total, previous_total), min(free, previous_free))
        else:
            filesystems[key] = (total, free)
    storage_total = sum(total for total, _ in filesystems.values())
    storage_free = sum(free for _, free in filesystems.values())

    if isinstance(health, dict) and health.get('version'):
        node.agent_version = str(health['version'])
    node.cpu_total = resources.get('cpu_logical')
    node.memory_total_mib = resources.get('memory_total_mib')
    node.memory_available_mib = resources.get('memory_available_mib')
    node.storage_total_bytes = storage_total
    node.storage_free_bytes = storage_free
    node.resource_sampled_at = now
    node.resource_is_stale = False
    node.last_seen_at = now
    node.consecutive_failures = 0
    node.last_error_code = ''
    node.last_error_message = ''

    missing = [
        value is None
        for value in (node.cpu_total, node.memory_total_mib, node.memory_available_mib)
    ]
    if node.status != NodeStatus.MAINTENANCE:
        node.status = NodeStatus.DEGRADED if any(missing) else NodeStatus.ONLINE

    node.save()
    logger.info(
        '节点采集成功',
        extra={'node_id': node.pk, 'status': node.status, 'result': 'success'},
    )
    return node


def collect_all_nodes() -> dict[str, int]:
    """对全部未注销节点执行一次采集。

    Returns:
        形如 {'total': n, 'online': n, 'offline': n, 'failed': n} 的汇总。
    """
    summary = {'total': 0, 'online': 0, 'offline': 0, 'failed': 0}
    for node in Node.objects.filter(is_deleted=False):
        summary['total'] += 1
        try:
            refresh_node(node)
        except Exception:
            summary['failed'] += 1
            logger.exception('节点采集中断', extra={'node_id': node.pk})
            continue
        if node.consecutive_failures:
            summary['failed'] += 1
        elif node.status == NodeStatus.OFFLINE:
            summary['offline'] += 1
        else:
            summary['online'] += 1
    return summary


def node_is_silenced(node: Node, now=None) -> bool:
    """判断节点心跳是否已静默超过阈值（用于展示与告警）。"""
    current = now or timezone.now()
    if node.last_seen_at is None:
        return True
    return current - node.last_seen_at >= timedelta(seconds=node.offline_after_seconds)
