"""对账与告警服务。

流程：检测 → 记录差异 → 安全修复 → 有破坏风险的转人工。
自动修复仅限观测状态等可安全纠正的差异，绝不删除域或磁盘。
"""

import logging

from django.utils import timezone

from apps.instances.models import Instance, ObservedState, ReservationStatus, ResourceReservation
from apps.monitoring.models import (
    Alert,
    AlertLevel,
    AlertStatus,
    AlertType,
    DiffKind,
    DiffResolution,
    ReconciliationDiff,
    ReconciliationRun,
)
from apps.nodes.client import AgentClient
from apps.nodes.models import Node
from common.errors import AppError

logger = logging.getLogger(__name__)

ALERT_LEVEL = {
    DiffKind.DB_INSTANCE_MISSING_DOMAIN: AlertLevel.CRITICAL,
    DiffKind.DOMAIN_NOT_IN_DB: AlertLevel.WARNING,
    DiffKind.INSTANCE_STATE_DRIFT: AlertLevel.INFO,
    DiffKind.RESERVATION_MISMATCH: AlertLevel.WARNING,
}


def _normalize(raw: str) -> str:
    """把 Agent 状态映射为观测状态。"""
    value = (raw or '').upper()
    return value if value in ObservedState.values else ObservedState.UNKNOWN


def _upsert_alert(
    kind: str,
    message: str,
    *,
    node=None,
    instance=None,
    resource_type: str = 'node',
    resource_id: str = '',
) -> None:
    """创建或刷新告警，同类同资源只保留一条活跃记录。"""
    alert, created = Alert.objects.get_or_create(
        type=kind,
        node=node,
        instance=instance,
        resource_type=resource_type,
        resource_id=resource_id,
        status=AlertStatus.ACTIVE,
        defaults={'message': message, 'level': ALERT_LEVEL.get(kind, AlertLevel.WARNING)},
    )
    if not created:
        alert.message = message
        alert.count += 1
        alert.save(update_fields=['message', 'count', 'last_seen_at'])


def _resolve_alerts(kind: str, still_active: set[tuple[str, str]], *, node=None) -> int:
    """把本次未再检测到的同类告警标记为已恢复。"""
    resolved = 0
    query = Alert.objects.filter(type=kind, status=AlertStatus.ACTIVE)
    if node is not None:
        query = query.filter(node=node)
    for alert in query:
        key = (alert.resource_type, alert.resource_id)
        if key in still_active:
            continue
        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = timezone.now()
        alert.save(update_fields=['status', 'resolved_at', 'last_seen_at'])
        resolved += 1
    return resolved


def reconcile_node(
    node: Node, *, client: AgentClient | None = None, run: ReconciliationRun | None = None
) -> dict:
    """对单个节点执行一次对账。

    Args:
        node: 目标节点。
        client: Agent 客户端，缺省按节点创建（测试可注入）。
        run: 所属对账批次，可为空（独立调用）。

    Returns:
        包含 drift / missing_domain / orphan_domain / expired_reservation 计数的汇总。

    Raises:
        AppError: 无法从节点获取域列表时抛出（对账失败，不做任何修改）。
    """
    agent = client or AgentClient(node.endpoint)
    domains = agent.domains()
    domain_states = {str(item.get('name')): str(item.get('state')) for item in domains}

    summary = {'drift': 0, 'missing_domain': 0, 'orphan_domain': 0, 'expired_reservation': 0}
    active_missing: set[tuple[str, str]] = set()
    active_drift: set[tuple[str, str]] = set()
    active_orphan: set[tuple[str, str]] = set()

    instances = Instance.objects.filter(node=node, is_deleted=False)
    for instance in instances:
        domain_name = instance.libvirt_domain_name
        if domain_name not in domain_states:
            summary['missing_domain'] += 1
            active_missing.add(('instance', str(instance.pk)))
            instance.observed_state = ObservedState.UNKNOWN
            instance.observed_state_is_stale = True
            instance.save(update_fields=['observed_state', 'observed_state_is_stale', 'updated_at'])
            ReconciliationDiff.objects.create(
                run=run,
                kind=DiffKind.DB_INSTANCE_MISSING_DOMAIN,
                node=node,
                resource_type='instance',
                resource_id=str(instance.pk),
                detail={'domain': domain_name, 'name': instance.name},
                resolution=DiffResolution.MANUAL,
            )
            _upsert_alert(
                AlertType.DB_INSTANCE_MISSING_DOMAIN,
                f'实例 {instance.name} 在宿主机上找不到对应域',
                node=node,
                instance=instance,
                resource_type='instance',
                resource_id=str(instance.pk),
            )
            continue

        state = _normalize(domain_states[domain_name])
        if state != instance.observed_state:
            summary['drift'] += 1
            active_drift.add(('instance', str(instance.pk)))
            ReconciliationDiff.objects.create(
                run=run,
                kind=DiffKind.INSTANCE_STATE_DRIFT,
                node=node,
                resource_type='instance',
                resource_id=str(instance.pk),
                detail={'before': instance.observed_state, 'after': state},
                resolution=DiffResolution.AUTO_FIXED,
            )
            instance.mark_observed(state)
            instance.save(
                update_fields=[
                    'observed_state',
                    'observed_state_updated_at',
                    'observed_state_is_stale',
                    'updated_at',
                ]
            )
            _upsert_alert(
                AlertType.INSTANCE_STATE_DRIFT,
                f'实例 {instance.name} 状态由 {state} 校正为当前值',
                node=node,
                instance=instance,
                resource_type='instance',
                resource_id=str(instance.pk),
            )
        domain_states.pop(domain_name, None)

    for name in domain_states:
        summary['orphan_domain'] += 1
        active_orphan.add(('domain', name))
        ReconciliationDiff.objects.create(
            run=run,
            kind=DiffKind.DOMAIN_NOT_IN_DB,
            node=node,
            resource_type='domain',
            resource_id=name,
            detail={'state': domain_states[name]},
            resolution=DiffResolution.MANUAL,
        )
        _upsert_alert(
            AlertType.DOMAIN_NOT_IN_DB,
            f'宿主机存在未登记的域 {name}',
            node=node,
            resource_type='domain',
            resource_id=name,
        )

    expired = ResourceReservation.objects.filter(
        node=node, status=ReservationStatus.HELD, expires_at__lt=timezone.now()
    )
    active_reservation: set[tuple[str, str]] = set()
    for reservation in expired:
        summary['expired_reservation'] += 1
        active_reservation.add(('reservation', str(reservation.pk)))
        ReconciliationDiff.objects.create(
            run=run,
            kind=DiffKind.RESERVATION_MISMATCH,
            node=node,
            resource_type='reservation',
            resource_id=str(reservation.pk),
            detail={
                'task': str(reservation.task_id),
                'expires_at': reservation.expires_at.isoformat(),
            },
            resolution=DiffResolution.MANUAL,
        )
        _upsert_alert(
            AlertType.RESERVATION_MISMATCH,
            '存在到期未处理的资源预留，需人工确认后释放',
            node=node,
            resource_id=str(reservation.pk),
        )

    _resolve_alerts(AlertType.DB_INSTANCE_MISSING_DOMAIN, active_missing, node=node)
    _resolve_alerts(AlertType.INSTANCE_STATE_DRIFT, active_drift, node=node)
    _resolve_alerts(AlertType.DOMAIN_NOT_IN_DB, active_orphan, node=node)
    _resolve_alerts(AlertType.RESERVATION_MISMATCH, active_reservation, node=node)
    return summary


def run_reconciliation(*, requested_by=None, nodes=None) -> ReconciliationRun:
    """对全部（或指定）节点执行对账并落库。

    Args:
        requested_by: 触发人，可为空。
        nodes: 节点查询集，缺省为全部未删除节点。

    Returns:
        对账批次记录。
    """
    targets = nodes if nodes is not None else Node.objects.filter(is_deleted=False)
    run = ReconciliationRun.objects.create(scope='all', status='RUNNING')
    totals = {
        'nodes': 0,
        'failed': 0,
        'drift': 0,
        'missing_domain': 0,
        'orphan_domain': 0,
        'expired_reservation': 0,
    }

    for node in targets:
        totals['nodes'] += 1
        try:
            summary = reconcile_node(node, run=run)
        except AppError as exc:
            totals['failed'] += 1
            logger.warning(
                '节点对账失败',
                extra={'node_id': node.pk, 'error_code': exc.code},
            )
            continue
        for key in ('drift', 'missing_domain', 'orphan_domain', 'expired_reservation'):
            totals[key] += summary[key]

    run.status = 'SUCCEEDED' if totals['failed'] == 0 else 'PARTIAL'
    run.finished_at = timezone.now()
    run.summary = totals
    run.save(update_fields=['status', 'finished_at', 'summary'])
    return run


def overview() -> dict:
    """构建监控概览数据。"""
    from django.db.models import Count

    from apps.nodes.models import Node

    node_stats = dict(
        Node.objects.filter(is_deleted=False).values_list('status').annotate(total=Count('id'))
    )
    instance_stats = dict(
        Instance.objects.filter(is_deleted=False)
        .values_list('observed_state')
        .annotate(total=Count('id'))
    )
    alerts = list(
        Alert.objects.filter(status=AlertStatus.ACTIVE)
        .order_by('-level', '-last_seen_at')[:20]
        .values('id', 'type', 'level', 'message', 'resource_type', 'resource_id', 'last_seen_at')
    )
    latest_run = ReconciliationRun.objects.order_by('-started_at').first()
    return {
        'nodes': node_stats,
        'instances': instance_stats,
        'active_alerts': alerts,
        'last_reconciliation': {
            'id': latest_run.pk if latest_run else None,
            'status': latest_run.status if latest_run else None,
            'finished_at': latest_run.finished_at if latest_run else None,
            'summary': latest_run.summary if latest_run else {},
        },
    }
