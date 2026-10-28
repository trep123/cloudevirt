"""实例创建服务：校验、资源预留与入队。

关键约束：
- 资源检查与预留必须在同一事务内，并对节点行加锁，避免并发超分；
- 事务内不调用 Agent，实际创建由任务执行器在事务提交后进行。
"""

import hashlib
import logging
import re
import secrets
import uuid as uuid_module
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
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
from apps.networks.models import Network
from apps.networks.services import validate_network_for_instance
from apps.nodes.access import user_can_access
from apps.nodes.models import NodePermission
from apps.tasks.models import Task, TaskType
from apps.tasks.services import enqueue
from common.errors import AppError, ErrorCode
from common.quota import enforce_quota

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
    allocated = Instance.objects.filter(node=node, is_deleted=False).exclude(
        reservations__status__in=[ReservationStatus.HELD, ReservationStatus.RELEASED]
    )
    for instance in allocated:
        used_vcpu += instance.vcpu
        used_memory += instance.memory_mib
    used_disk = 0
    for disk in Disk.objects.filter(instance__in=allocated):
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
    if type(memory_mib) is int and memory_mib < 128:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            '内存至少为 128 MiB',
            details={'memory_mib': ['不能低于 128 MiB']},
        )
    for field_name, value, maximum in (
        ('vcpu', vcpu, limit('INSTANCE_MAX_VCPU', 64)),
        ('memory_mib', memory_mib, limit('INSTANCE_MAX_MEMORY_MIB', 131072)),
        ('disk_gib', disk_gib, limit('INSTANCE_MAX_DISK_GIB', 2048)),
    ):
        if type(value) is not int or value <= 0:
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
    start_after_create: bool = True,
    template: int | None = None,
    template_version: int | None = None,
    data_disks: list[int] | None = None,
    additional_networks: list[str] | None = None,
    hardware: dict | None = None,
    initialization: dict | None = None,
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
    data_disks = data_disks or []
    additional_networks = additional_networks or []
    if len(data_disks) > 8 or any(
        type(size) is not int or not 1 <= size <= 2048 for size in data_disks
    ):
        raise AppError(ErrorCode.INVALID_ARGUMENT, '数据盘配置无效')
    extra_networks = [validate_network_for_instance(name) for name in additional_networks]
    if len(extra_networks) > 7 or any(n is None for n in extra_networks):
        raise AppError(ErrorCode.INVALID_ARGUMENT, '附加网络无效')
    total_disk_gib = disk_gib + sum(data_disks)
    hardware = hardware or {}
    from apps.instances.hardware import validate_hardware_policy

    validate_hardware_policy(
        {
            'hardware': hardware,
            'initialization': initialization,
            'vcpu': vcpu,
            'image': image,
            'template_version': template_version,
        },
        user,
    )
    from apps.accounts.administration import limit_nodes

    if node.pk not in limit_nodes(user, [node.pk], 'instances.add_instance'):
        raise AppError(ErrorCode.PERMISSION_DENIED, '目标节点不在角色或用户的创建授权范围内')
    if not user_can_access(user, node, NodePermission.OPERATE):
        raise AppError(ErrorCode.PERMISSION_DENIED, '没有目标节点的操作权限')
    scoped_key = (
        hashlib.sha256(f'{user.pk}:{idempotency_key}'.encode()).hexdigest()
        if idempotency_key
        else None
    )

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

    disk_bytes = total_disk_gib * GIB
    instance_uuid = uuid_module.uuid4()
    domain_name = domain_name_for(instance_uuid)
    disk_name = f'{instance_uuid}-system.qcow2'

    with transaction.atomic():
        locked_node = type(node).objects.select_for_update().get(pk=node.pk)
        # Also serialize cross-node requests and idempotency lookup for this account.
        quota_user = get_user_model().objects.select_for_update().get(pk=user.pk)
        image = type(image).objects.select_for_update().get(pk=image.pk)
        if image.is_deleted or image.status != ImageStatus.READY:
            raise AppError(ErrorCode.CONFLICT, '镜像已删除或尚未校验完成')
        if image.node_id and image.node_id != locked_node.pk:
            raise AppError(ErrorCode.CONFLICT, '镜像文件位于其他节点，请选择镜像所属节点')
        if scoped_key:
            previous = Task.objects.filter(
                idempotency_key=scoped_key, requested_by=user, type=TaskType.INSTANCE_CREATE
            ).first()
            if previous:
                instance = Instance.objects.filter(
                    pk=previous.resource_id, created_by=user, is_deleted=False
                ).first()
                if (
                    instance is None
                    or (
                        instance.name,
                        instance.node_id,
                        instance.image_id,
                        instance.vcpu,
                        instance.memory_mib,
                        instance.disk_gib,
                        instance.network_name,
                        instance.autostart,
                    )
                    != (
                        name,
                        node.pk,
                        image.pk,
                        vcpu,
                        memory_mib,
                        disk_gib,
                        network_name,
                        autostart,
                    )
                    or instance.creation_config.get('start_after_create', True)
                    != start_after_create
                    or instance.creation_config.get('template') != template
                    or instance.creation_config.get('hardware', {}) != hardware
                    or instance.creation_config.get('initialization') != initialization
                    or instance.creation_config.get('template_version') != template_version
                    or instance.creation_config.get('data_disks', []) != data_disks
                    or instance.creation_config.get('additional_networks', [])
                    != additional_networks
                ):
                    raise AppError(ErrorCode.CONFLICT, '幂等键已用于其他配置，请先核对原任务')
                return instance, previous
        enforce_quota(quota_user, vcpu=vcpu, memory_mib=memory_mib, disk_gib=total_disk_gib)
        if network is not None:
            network = (
                Network.objects.select_for_update().filter(pk=network.pk, is_deleted=False).first()
            )
            if network is None or not network.is_usable or network.name != network_name:
                raise AppError(ErrorCode.CONFLICT, '网络配置已变化，请刷新后重新提交')
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
            desired_state='RUNNING' if start_after_create else 'SHUTOFF',
            initialization_status='PENDING' if initialization else 'NOT_CONFIGURED',
            creation_config={
                'schema_version': 1,
                'hardware': hardware,
                'initialization': initialization,
                'data_disks': data_disks,
                'additional_networks': additional_networks,
                'network_specs': [
                    {
                        'network': n.name,
                        'network_type': n.type,
                        'network_bridge': n.bridge,
                        'vlan_id': n.vlan_id or 0,
                    }
                    for n in extra_networks
                ],
                'start_after_create': start_after_create,
                'autostart': autostart,
                'template': template,
                'template_version': template_version,
                'vcpu': vcpu,
                'memory_mib': memory_mib,
                'disk_gib': disk_gib,
                'network_name': network_name,
                'image': {
                    'id': image.pk,
                    'relative_path': image.relative_path,
                    'format': image.format,
                    'checksum': image.checksum_sha256,
                },
            },
            vnc_password=secrets.token_hex(4),
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
        for index, size in enumerate(data_disks, 1):
            filename = f'{instance_uuid}-data-{index}.qcow2'
            Disk.objects.create(
                instance=instance,
                role=DiskRole.DATA,
                name=filename,
                relative_path=filename,
                size_gib=size,
                target_dev='vd' + chr(ord('a') + index),
                status=DiskStatus.CREATING,
            )
        task = enqueue(
            task_type=TaskType.INSTANCE_CREATE,
            resource_type='instance',
            resource_id=str(instance.pk),
            requested_by=user,
            payload={
                'instance_uuid': str(instance_uuid),
                'creation_config': {
                    **instance.creation_config,
                    'template_version': template_version,
                },
                'domain_name': domain_name,
                'vcpu': vcpu,
                'memory_mib': memory_mib,
                'disk_gib': disk_gib,
                'disk_relative_path': disk_name,
                'network_name': network_name,
                'network_type': network.type if network else '',
                'network_bridge': network.bridge if network else '',
                'vlan_id': network.vlan_id if network else None,
            },
            idempotency_key=scoped_key,
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
