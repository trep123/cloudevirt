"""实例创建服务：校验、资源预留与入队。

关键约束：
- 资源检查与预留必须在同一事务内，并对节点行加锁，避免并发超分；
- 事务内不调用 Agent，实际创建由任务执行器在事务提交后进行。
"""

import logging
import re
import uuid as uuid_module
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.images.models import ImageStatus
from apps.instances.models import (
    Disk,
    DiskRole,
    DiskStatus,
    Instance,
    ReservationStatus,
    ResourceReservation,
)
from apps.networks.services import validate_network_for_instance
from apps.tasks.models import TaskType
from apps.tasks.services import enqueue
from common.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)

NAME_PATTERN = re.compile(r'^[A-Za-z0-9]([A-Za-z0-9-]{1,62}[A-Za-z0-9])$')
GIB = 1024 * 1024 * 1024


def domain_name_for(instance_uuid) -> str:
    """生成 libvirt 域名，避免与用户可见名冲突。"""
    return f'cv-{str(instance_uuid)[:8]}'


def limit(name: str, fallback: int) -> int:
    """读取资源上限配置。"""
    return int(getattr(settings, name, fallback))


def available_resources(node) -> dict[str, int]:
    """计算节点可用于新实例的资源（已扣除在途预留与在用资源）。

    Args:
        node: 目标节点。

    Returns:
        含 vcpu / memory_mib / disk_bytes 可用量的字典。
    """
    reserved = ResourceReservation.objects.filter(
        node=node, status=ReservationStatus.HELD
    ).aggregate(
        vcpu=Sum('vcpu_reserved'),
        memory=Sum('memory_reserved_mib'),
        disk=Sum('disk_reserved_bytes'),
    )
    used_vcpu = 0
    used_memory = 0
    for instance in Instance.objects.filter(node=node, is_deleted=False).exclude(
        observed_state='SHUTOFF'
    ):
        used_vcpu += instance.vcpu
        used_memory += instance.memory_mib
    used_disk = 0
    for disk in Disk.objects.filter(instance__node=node, instance__is_deleted=False):
        used_disk += (disk.size_gib or 0) * GIB

    return {
        'vcpu': (node.cpu_total or 0) - used_vcpu - (reserved['vcpu'] or 0),
        'memory_mib': (node.memory_total_mib or 0) - used_memory - (reserved['memory'] or 0),
        'disk_bytes': (node.storage_free_bytes or 0) - used_disk - (reserved['disk'] or 0),
    }


def validate_spec(*, name: str, vcpu: int, memory_mib: int, disk_gib: int) -> None:
    """校验实例规格是否符合命名规则与上限。

    Args:
        name: 实例名。
        vcpu: vCPU 数量。
        memory_mib: 内存 MiB。
        disk_gib: 系统盘 GiB。

    Raises:
        AppError: 任一字段非法时抛出 VALIDATION_ERROR。
    """
    if not NAME_PATTERN.match(name or ''):
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            '实例名称格式非法',
            details={'name': ['3-64 位字母、数字或连字符，且不能以连字符开头结尾']},
        )
    for field_name, value, maximum in (
        ('vcpu', vcpu, limit('INSTANCE_MAX_VCPU', 64)),
        ('memory_mib', memory_mib, limit('INSTANCE_MAX_MEMORY_MIB', 131072)),
        ('disk_gib', disk_gib, limit('INSTANCE_MAX_DISK_GIB', 2048)),
    ):
        if not isinstance(value, int) or value <= 0:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                '规格必须为正整数',
                details={field_name: ['必须大于 0']},
            )
        if value > maximum:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                '规格超过平台上限',
                details={field_name: [f'不能超过 {maximum}']},
            )


def create_instance(
    *,
    user,
    name: str,
    node,
    image,
    vcpu: int,
    memory_mib: int,
    disk_gib: int,
    network_name: str = '',
    autostart: bool = False,
    idempotency_key: str | None = None,
) -> tuple[Instance, object]:
    """创建实例记录、磁盘、任务与资源预留。

    Args:
        user: 发起人。
        name: 实例名。
        node: 目标节点。
        image: 镜像。
        vcpu: vCPU 数量。
        memory_mib: 内存 MiB。
        disk_gib: 系统盘 GiB。
        network_name: 网络名称，空表示使用节点默认。
        autostart: 是否开机自启。
        idempotency_key: 幂等键。

    Returns:
        (实例, 任务) 元组。

    Raises:
        AppError: 参数非法、节点不可调度、镜像不可用或资源不足。
    """
    validate_spec(name=name, vcpu=vcpu, memory_mib=memory_mib, disk_gib=disk_gib)

    if image.status != ImageStatus.READY or image.is_deleted:
        raise AppError(
            ErrorCode.CONFLICT,
            '镜像不可用',
            details={'image': [f'当前状态为 {image.status}']},
        )
    network = validate_network_for_instance(network_name)
    if network is not None:
        network_name = network.name

    if not node.is_schedulable:
        raise AppError(
            ErrorCode.NODE_OFFLINE,
            '节点不可调度',
            details={'node': [f'当前状态为 {node.status}']},
        )

    disk_bytes = disk_gib * GIB
    instance_uuid = uuid_module.uuid4()
    domain_name = domain_name_for(instance_uuid)
    disk_name = f'{instance_uuid}-system.qcow2'

    with transaction.atomic():
        locked_node = type(node).objects.select_for_update().get(pk=node.pk)
        if not locked_node.is_schedulable:
            raise AppError(ErrorCode.NODE_OFFLINE, '节点不可调度')

        if Instance.objects.filter(node=locked_node, name=name, is_deleted=False).exists():
            raise AppError(
                ErrorCode.CONFLICT,
                '同名实例已存在',
                details={'name': ['该节点下已存在同名实例']},
            )

        available = available_resources(locked_node)
        shortages = []
        if vcpu > available['vcpu']:
            shortages.append('vcpu')
        if memory_mib > available['memory_mib']:
            shortages.append('memory_mib')
        if disk_bytes > available['disk_bytes']:
            shortages.append('disk_bytes')
        if shortages:
            raise AppError(
                ErrorCode.INSUFFICIENT_RESOURCE,
                '节点资源不足',
                details={'shortage': shortages, 'available': available},
            )

        instance = Instance.objects.create(
            uuid=instance_uuid,
            name=name,
            libvirt_domain_name=domain_name,
            node=locked_node,
            image=image,
            network_name=network_name,
            vcpu=vcpu,
            memory_mib=memory_mib,
            disk_gib=disk_gib,
            autostart=autostart,
            created_by=user,
        )
        Disk.objects.create(
            instance=instance,
            role=DiskRole.SYSTEM,
            name=disk_name,
            relative_path=disk_name,
            size_gib=disk_gib,
            status=DiskStatus.CREATING,
        )
        task = enqueue(
            task_type=TaskType.INSTANCE_CREATE,
            resource_type='instance',
            resource_id=str(instance.pk),
            requested_by=user,
            payload={
                'instance_uuid': str(instance_uuid),
                'domain_name': domain_name,
                'vcpu': vcpu,
                'memory_mib': memory_mib,
                'disk_gib': disk_gib,
                'disk_relative_path': disk_name,
                'network_name': network_name,
            },
            idempotency_key=idempotency_key,
        )
        instance.current_task = task
        instance.operation_status = 'PENDING'
        instance.save(update_fields=['current_task', 'operation_status', 'updated_at'])
        ResourceReservation.objects.create(
            node=locked_node,
            task=task,
            instance=instance,
            vcpu_reserved=vcpu,
            memory_reserved_mib=memory_mib,
            disk_reserved_bytes=disk_bytes,
            expires_at=timezone.now() + timedelta(minutes=15),
        )

    logger.info(
        '实例创建任务已入队',
        extra={'instance_id': instance.pk, 'task_id': str(task.pk), 'node_id': locked_node.pk},
    )
    return instance, task


def commit_reservation(instance) -> None:
    """任务成功后把预留转为已分配。"""
    ResourceReservation.objects.filter(instance=instance, status=ReservationStatus.HELD).update(
        status=ReservationStatus.COMMITTED, updated_at=timezone.now()
    )


def release_reservation(instance) -> None:
    """确认资源未创建或已清理后释放预留。"""
    ResourceReservation.objects.filter(instance=instance, status=ReservationStatus.HELD).update(
        status=ReservationStatus.RELEASED, updated_at=timezone.now()
    )
