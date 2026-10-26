"""审计记录服务：统一入口，保证四要素（操作者、对象、结果、时间）齐全。"""

import logging
from typing import Any

from django.contrib.auth.models import AbstractUser
from django.db import DatabaseError

from apps.audit.models import AuditEvent, AuditResult
from common.logging import get_request_id, get_task_id

logger = logging.getLogger(__name__)


def record_audit(
    *,
    action: str,
    actor: AbstractUser | None = None,
    actor_username: str = '',
    target_type: str = '',
    target_id: str = '',
    result: str = AuditResult.SUCCESS,
    details: dict[str, Any] | None = None,
    ip: str | None = None,
    task_id: str | None = None,
) -> AuditEvent | None:
    """写入一条审计事件，写入失败时记录日志但不阻断主流程。

    Args:
        action: 审计动作，取自 AuditAction。
        actor: 操作者，可为空（如登录失败）。
        actor_username: 操作者账号快照，用户删除后仍可读。
        target_type: 操作对象类型。
        target_id: 操作对象标识。
        result: 结果，默认 SUCCESS。
        details: 变更前后关键字段（必须脱敏）。
        ip: 来源 IP。
        task_id: 关联任务 ID。

    Returns:
        创建成功的审计事件；写入失败时返回 None。
    """
    username = actor_username or (actor.get_username() if actor else '')
    try:
        return AuditEvent.objects.create(
            actor=actor if actor and actor.pk else None,
            actor_username=username,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id else '',
            result=result,
            request_id=get_request_id(),
            task_id=task_id or get_task_id() or None,
            ip=ip,
            details=details or {},
        )
    except DatabaseError:
        logger.exception('审计写入失败', extra={'action': action})
        return None


def record_denied(
    *,
    action: str,
    actor: AbstractUser | None,
    target_type: str = '',
    target_id: str = '',
    codename: str = '',
) -> None:
    """记录一次权限被拒事件。

    Args:
        action: 被拒绝的动作。
        actor: 操作者。
        target_type: 操作对象类型。
        target_id: 操作对象标识。
        codename: 缺失的权限码。
    """
    record_audit(
        action=action,
        actor=actor,
        target_type=target_type,
        target_id=target_id,
        result=AuditResult.DENIED,
        details={'required_permission': codename},
    )
