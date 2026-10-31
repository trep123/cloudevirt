"""Administrator-only, cold hardware changes with durable resource reservations."""

import hashlib
import secrets
import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.administration import require_admin
from apps.accounts.roles import is_admin
from apps.audit.services import record_audit
from apps.instances.actions import ensure_no_active_task
from apps.instances.hardware import StrictInput
from apps.instances.models import Disk, Instance, ResourceReservation
from apps.instances.serializers import DiskSerializer
from apps.instances.services import GIB, available_resources
from apps.networks.models import InstanceNIC, IPLease, Network
from apps.networks.services import validate_network_for_instance
from apps.nodes.client import AgentClient
from apps.nodes.models import Node
from apps.tasks.models import Task, TaskType
from apps.tasks.services import enqueue
from common.errors import AppError, ErrorCode
from common.permissions import CanViewInstance, RequiresPasswordChange, check_permission
from common.quota import quota_for
from common.scope import instances_for


class DeviceInput(StrictInput):
    operation = serializers.ChoiceField(
        choices=[
            'compute',
            'disk-add',
            'disk-attach',
            'disk-detach',
            'disk-resize',
            'nic-add',
            'nic-remove',
            'cdrom-set',
            'cdrom-remove',
        ]
    )
    live = serializers.BooleanField(required=False)
    image_id = serializers.IntegerField(min_value=1, required=False)
    target = serializers.RegexField(r'^sda$', required=False)
    vcpu = serializers.IntegerField(min_value=1, max_value=128, required=False)
    memory_mib = serializers.IntegerField(min_value=128, max_value=1048576, required=False)
    disk_id = serializers.IntegerField(min_value=1, required=False)
    size_gib = serializers.IntegerField(min_value=1, max_value=2048, required=False)
    bus = serializers.ChoiceField(choices=['virtio', 'sata'], required=False)
    network_name = serializers.CharField(max_length=64, required=False, allow_blank=False)
    model = serializers.ChoiceField(choices=['virtio', 'e1000e'], required=False)
    mac = serializers.RegexField(r'^(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$', required=False)

    def validate(self, data):
        required = {
            'compute': {'vcpu', 'memory_mib'},
            'disk-add': {'size_gib', 'bus'},
            'disk-attach': {'disk_id'},
            'disk-detach': {'disk_id'},
            'disk-resize': {'disk_id', 'size_gib'},
            'nic-add': {'network_name', 'model'},
            'nic-remove': {'mac'},
            'cdrom-set': {'target', 'image_id'},
            'cdrom-remove': {'target'},
        }[data['operation']]
        if data.get('live') and data['operation'] != 'nic-add':
            raise serializers.ValidationError({'live': '热变更仅支持新增网卡'})
        if set(data) - {'operation', 'live'} != required:
            raise serializers.ValidationError(f'此操作只接受以下字段：{sorted(required)}')
        return data


def cold_instance(instance):
    if not instance.node.is_schedulable:
        raise AppError(ErrorCode.NODE_OFFLINE, '节点不可用')
    if instance.observed_state != 'SHUTOFF' or instance.observed_state_is_stale:
        raise AppError(ErrorCode.CONFLICT, '请先正常关闭虚拟机，等待节点确认已关机')


def authorize_hardware(user, instance, operation):
    """Grant ordinary users only network attachment and their own data disk changes."""
    if is_admin(user):
        require_admin(user, 'instances.change_instance')
        permission = 'instances.change_instance'
    else:
        if instance.created_by_id != user.pk:
            raise AppError(ErrorCode.PERMISSION_DENIED, '只能操作自己的虚拟机')
        if operation == 'nic-add':
            permission = 'instances.connect_network_instance'
            check_permission(user, 'networks.view_network')
        elif operation in {'disk-add', 'disk-attach', 'disk-detach'}:
            permission = 'instances.manage_data_disk_instance'
        else:
            raise AppError(ErrorCode.PERMISSION_DENIED, '此硬件操作仅平台管理员可执行')
    check_permission(user, permission, target_type='instance', target_id=str(instance.pk))


class InstanceHardwareView(APIView):
    permission_classes = [CanViewInstance, RequiresPasswordChange]

    def get(self, request, pk):
        instance = get_object_or_404(instances_for(request.user), pk=pk)
        result = AgentClient(instance.node.endpoint).domain_hardware(
            instance.libvirt_domain_name,
            storage_pool=instance.storage_pool.name if instance.storage_pool_id else '',
        )
        if result.get('uuid') != str(instance.uuid):
            raise AppError(ErrorCode.CONFLICT, '节点域 UUID 不匹配')
        records = {d.relative_path: d for d in instance.disks.exclude(status='DELETED')}
        for disk in result.get('disks', []):
            record = records.get(disk.get('relative_path'))
            disk['disk_id'] = record.pk if record else None
            disk['role'] = record.role if record else 'UNKNOWN'
        result['retained_disks'] = DiskSerializer(
            instance.disks.filter(status='DETACHED'), many=True
        ).data
        result['requires_shutdown'] = True
        return Response(result)

    @transaction.atomic
    def post(self, request, pk):
        visible = get_object_or_404(instances_for(request.user), pk=pk)
        node = Node.objects.select_for_update().get(pk=visible.node_id)
        owner = (
            get_user_model().objects.select_for_update().get(pk=visible.created_by_id)
            if visible.created_by_id
            else request.user
        )
        instance = (
            Instance.objects.select_for_update().select_related('node').get(pk=pk, is_deleted=False)
        )
        serializer = DeviceInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        authorize_hardware(request.user, instance, data['operation'])
        raw_key = request.headers.get('Idempotency-Key', '')
        if len(raw_key) > 128:
            raise AppError(ErrorCode.INVALID_ARGUMENT, '幂等键过长')
        scoped_key = (
            hashlib.sha256(f'hardware:{request.user.pk}:{pk}:{raw_key}'.encode()).hexdigest()
            if raw_key
            else None
        )
        if scoped_key:
            previous = Task.objects.filter(
                type=TaskType.INSTANCE_HARDWARE,
                idempotency_key=scoped_key,
                requested_by=request.user,
            ).first()
            if previous:
                if previous.payload.get('request') != data:
                    raise AppError(ErrorCode.CONFLICT, '此幂等键已用于其他硬件配置，请先核对原任务')
                return Response(
                    {
                        'task': {
                            'id': str(previous.pk),
                            'status': previous.status,
                            'status_url': f'/api/v1/tasks/{previous.pk}',
                        }
                    },
                    status=202,
                )
        if data.get('live'):
            if (
                not instance.node.is_schedulable
                or instance.observed_state != 'RUNNING'
                or instance.observed_state_is_stale
                or not instance.observed_state_updated_at
                or instance.observed_state_updated_at < timezone.now() - timedelta(seconds=60)
            ):
                raise AppError(ErrorCode.CONFLICT, '热接入要求虚拟机处于已确认的运行状态')
            if (
                AgentClient(node.endpoint).get_json('/api/v1/node/capabilities').get('nic_hotplug')
                is not True
            ):
                raise AppError(ErrorCode.CONFLICT, '节点尚不支持网卡热接入，请升级 Agent')
        else:
            cold_instance(instance)
        if instance.reservations.filter(status='HELD').exists():
            raise AppError(ErrorCode.CONFLICT, '创建任务仍保留资源，请先核对创建结果')
        ensure_no_active_task(instance)
        if ResourceReservation.objects.filter(
            task__type=TaskType.INSTANCE_HARDWARE, task__resource_id=str(pk), status='HELD'
        ).exists():
            raise AppError(
                ErrorCode.CONFLICT, '存在未核对的硬件变更，请先在任务中心核对并重试原任务'
            )
        op = data['operation']
        payload = {'operation': op, 'uuid': str(instance.uuid)}
        if data.get('live'):
            payload['live'] = True
        meta = {}
        delta = {'vcpu': 0, 'memory_mib': 0, 'disk_gib': 0}
        disk = None
        if op == 'compute':
            payload.update(vcpu=data['vcpu'], memory_mib=data['memory_mib'])
            delta.update(
                vcpu=max(data['vcpu'] - instance.vcpu, 0),
                memory_mib=max(data['memory_mib'] - instance.memory_mib, 0),
            )
            if (
                instance.creation_config.get('hardware', {}).get('cpu_quota_percent', 0)
                > data['vcpu'] * 100
            ):
                raise AppError(ErrorCode.CONFLICT, '现有 CPU 配额超过目标 vCPU 上限，不能自动调整')
        elif op.startswith('disk-'):
            if op == 'disk-add':
                attached = instance.disks.exclude(status__in=['DETACHED', 'DELETED'])
                if attached.count() >= 9:
                    raise AppError(ErrorCode.CONFLICT, '最多支持 9 块磁盘')
                prefix = 'vd' if data['bus'] == 'virtio' else 'sd'
                used = set(attached.values_list('target_dev', flat=True))
                target = next(
                    (
                        prefix + chr(letter)
                        for letter in range(ord('b') if prefix == 'vd' else ord('c'), ord('z') + 1)
                        if prefix + chr(letter) not in used
                    ),
                    None,
                )
                if not target:
                    raise AppError(ErrorCode.CONFLICT, '无可用设备号')
                filename = f'{instance.uuid}-hw-{uuid.uuid4().hex[:12]}.qcow2'
                meta.update(
                    filename=filename, target=target, bus=data['bus'], size_gib=data['size_gib']
                )
                delta['disk_gib'] = data['size_gib']
                payload.update(
                    relative_path=filename,
                    target=target,
                    bus=data['bus'],
                    size_gib=data['size_gib'],
                )
            else:
                disk = get_object_or_404(instance.disks.select_for_update(), pk=data['disk_id'])
                if disk.status not in ['READY', 'DETACHED']:
                    raise AppError(ErrorCode.CONFLICT, '磁盘状态不允许此操作')
                if op in ['disk-attach', 'disk-detach'] and disk.role == 'SYSTEM':
                    raise AppError(ErrorCode.CONFLICT, '禁止卸载或替换系统盘')
                if not is_admin(request.user) and disk.role != 'DATA':
                    raise AppError(ErrorCode.PERMISSION_DENIED, '只能管理自己的数据盘')
                if op == 'disk-attach' and disk.status != 'DETACHED':
                    raise AppError(ErrorCode.CONFLICT, '磁盘未卸载')
                if op != 'disk-attach' and disk.status != 'READY':
                    raise AppError(ErrorCode.CONFLICT, '请先挂载磁盘')
                if op == 'disk-resize' and data['size_gib'] <= disk.size_gib:
                    raise AppError(ErrorCode.INVALID_ARGUMENT, '只能扩容，禁止缩小或重复尺寸')
                delta['disk_gib'] = max(data.get('size_gib', disk.size_gib) - disk.size_gib, 0)
                payload.update(
                    relative_path=disk.relative_path,
                    target=disk.target_dev,
                    bus=disk.bus,
                    size_gib=data.get('size_gib', disk.size_gib),
                )
                meta['disk_id'] = disk.pk
                if op == 'disk-attach':
                    used = set(
                        instance.disks.exclude(status__in=['DETACHED', 'DELETED'])
                        .exclude(pk=disk.pk)
                        .values_list('target_dev', flat=True)
                    )
                    if payload['target'] in used:
                        prefix = 'vd' if disk.bus == 'virtio' else 'sd'
                        target = next(
                            (
                                prefix + chr(letter)
                                for letter in range(
                                    ord('b') if prefix == 'vd' else ord('c'), ord('z') + 1
                                )
                                if prefix + chr(letter) not in used
                            ),
                            None,
                        )
                        if target is None:
                            raise AppError(ErrorCode.CONFLICT, '无可用磁盘设备号')
                        payload['target'] = target
        elif op in {'cdrom-set', 'cdrom-remove'}:
            if (
                instance.disks.filter(target_dev=data['target'])
                .exclude(status__in=['DETACHED', 'DELETED'])
                .exists()
            ):
                raise AppError(ErrorCode.CONFLICT, '安装光驱设备号已被磁盘占用，禁止替换')
            payload['target'] = data['target']
            if op == 'cdrom-set':
                from apps.images.models import Image

                image = get_object_or_404(
                    Image,
                    pk=data['image_id'],
                    is_deleted=False,
                    status='READY',
                    format='ISO',
                    node=node,
                )
                payload.update(
                    image_relative_path=image.relative_path,
                    image_storage_pool=image.storage_pool.name if image.storage_pool_id else '',
                )
                meta['image_id'] = image.pk
        elif op == 'nic-add':
            if instance.network_interfaces.count() >= 8:
                raise AppError(ErrorCode.CONFLICT, '最多支持 8 个网卡')
            network = validate_network_for_instance(data['network_name'], instance.node)
            if network is None or not network.is_usable:
                raise AppError(ErrorCode.CONFLICT, '网络不可用')
            network = Network.objects.select_for_update().get(pk=network.pk)
            if (
                network.is_management
                or instance.network_interfaces.filter(network=network).exists()
            ):
                raise AppError(ErrorCode.CONFLICT, '管理网络或已连接网络不能重复接入')
            mac = '02:' + ':'.join(f'{b:02x}' for b in secrets.token_bytes(5))
            payload.update(
                mac=mac,
                model=data['model'],
                network={
                    'network': network.name,
                    'network_type': network.type,
                    'network_bridge': network.bridge,
                    'vlan_id': network.vlan_id or 0,
                },
            )
            meta['network_id'] = network.pk
            meta['device_id'] = 'nic-hw-' + uuid.uuid4().hex[:6]
        else:
            mac = data['mac'].lower()
            if IPLease.objects.filter(nic__instance=instance, nic__mac=mac).exists():
                raise AppError(
                    ErrorCode.CONFLICT, '网卡存在静态 IP 租约记录，需先处理地址配置，暂不自动移除'
                )
            payload['mac'] = mac
        available = available_resources(node)
        if delta['disk_gib'] > 0 and instance.storage_pool_id:
            from apps.infrastructure.placement import pool_available_bytes

            available['disk_bytes'] = pool_available_bytes(node, instance.storage_pool)
        if any(
            delta[k] > 0 and delta[k] > available[v]
            for k, v in [('vcpu', 'vcpu'), ('memory_mib', 'memory_mib')]
        ) or (delta['disk_gib'] > 0 and delta['disk_gib'] * GIB > available['disk_bytes']):
            raise AppError(ErrorCode.INSUFFICIENT_RESOURCE, '节点容量不足')
        quota = quota_for(owner)
        pending = ResourceReservation.objects.filter(
            status='HELD',
            task__type=TaskType.INSTANCE_HARDWARE,
            task__resource_id__in=[
                str(pk)
                for pk in Instance.objects.filter(created_by=owner, is_deleted=False).values_list(
                    'pk', flat=True
                )
            ],
        ).select_related('task')
        for held in pending:
            quota['used']['vcpu'] += held.vcpu_reserved
            quota['used']['memory_mib'] += held.memory_reserved_mib
            if held.task.payload.get('change', {}).get('operation') == 'disk-resize':
                quota['used']['disk_gib'] += held.disk_reserved_bytes // GIB
        if quota['enforced'] and any(
            quota['used'][k] + delta[k] > quota['limits'][k] for k in delta
        ):
            raise AppError(ErrorCode.INSUFFICIENT_RESOURCE, '资源所有者配额不足')
        task = enqueue(
            task_type=TaskType.INSTANCE_HARDWARE,
            resource_type='instance',
            resource_id=str(pk),
            requested_by=request.user,
            payload={'change': payload, 'metadata': meta, 'request': data},
            idempotency_key=scoped_key,
            max_attempts=1,
        )
        ResourceReservation.objects.create(
            node=node,
            storage_pool=instance.storage_pool,
            task=task,
            vcpu_reserved=delta['vcpu'],
            memory_reserved_mib=delta['memory_mib'],
            disk_reserved_bytes=delta['disk_gib'] * GIB,
            expires_at=timezone.now() + timedelta(hours=24),
        )
        if op == 'disk-add':
            disk = Disk.objects.create(
                instance=instance,
                role='DATA',
                name=meta['filename'],
                relative_path=meta['filename'],
                size_gib=meta['size_gib'],
                target_dev=meta['target'],
                bus=meta['bus'],
                status='CREATING',
            )
            meta['disk_id'] = disk.pk
            task.payload['metadata'] = meta
            task.save(update_fields=['payload'])
        instance.current_task = task
        instance.operation_status = 'PENDING'
        instance.save(update_fields=['current_task', 'operation_status', 'updated_at'])
        record_audit(
            action='INSTANCE_HARDWARE_CHANGE',
            actor=request.user,
            target_type='instance',
            target_id=str(pk),
            task_id=str(task.pk),
            details={'operation': op, 'requested': data, 'phase': 'submitted'},
        )
        return Response(
            {
                'task': {
                    'id': str(task.pk),
                    'status': task.status,
                    'status_url': f'/api/v1/tasks/{task.pk}',
                }
            },
            status=202,
        )


def verify_result(result, change):
    if not isinstance(result, dict):
        return False
    if result.get('uuid') != change['uuid']:
        return False
    op = change['operation']
    if op in {'cdrom-set', 'cdrom-remove'}:
        device = next(
            (item for item in result.get('cdroms', []) if item.get('target') == change['target']),
            None,
        )
        return (device is None) if op == 'cdrom-remove' else bool(device and device.get('mounted'))
    if op == 'compute':
        return (
            result.get('vcpu') == change['vcpu']
            and result.get('memory_mib') == change['memory_mib']
        )
    if op.startswith('disk-'):
        disk = next(
            (d for d in result.get('disks', []) if d.get('target') == change['target']), None
        )
        if op == 'disk-detach':
            return disk is None
        return bool(
            disk
            and disk.get('relative_path') == change['relative_path']
            and disk.get('size_bytes') == change['size_gib'] * GIB
        )
    nic = next(
        (n for n in result.get('nics', []) if n.get('mac', '').lower() == change['mac']), None
    )
    if op == 'nic-remove':
        return nic is None
    network = change['network']
    return bool(
        nic
        and nic.get('model') == change['model']
        and nic.get('source') in [network['network'], network['network_bridge']]
    )


def execute_hardware_change(task):
    instance = Instance.objects.select_related('node').get(pk=task.resource_id, is_deleted=False)
    change = task.payload['change']
    meta = task.payload['metadata']
    try:
        authorize_hardware(task.requested_by, instance, change['operation'])
        if change['operation'] == 'cdrom-set':
            from apps.images.models import Image

            image = Image.objects.filter(
                pk=meta['image_id'],
                node=instance.node,
                is_deleted=False,
                status='READY',
                format='ISO',
            ).first()
            if (
                image is None
                or image.relative_path != change['image_relative_path']
                or (image.storage_pool.name if image.storage_pool_id else '')
                != change['image_storage_pool']
            ):
                raise AppError(ErrorCode.CONFLICT, '安装镜像状态或位置已变化，请重新提交')
        if change['operation'] in {'disk-attach', 'disk-detach'} and not is_admin(
            task.requested_by
        ):
            disk = instance.disks.get(pk=meta['disk_id'])
            if disk.role != 'DATA':
                raise AppError(ErrorCode.PERMISSION_DENIED, '只能管理自己的数据盘')
        if change['operation'] == 'nic-add':
            network = validate_network_for_instance(change['network']['network'], instance.node)
            if (
                network.pk != meta['network_id']
                or network.type != change['network']['network_type']
                or network.bridge != change['network']['network_bridge']
                or (network.vlan_id or 0) != change['network']['vlan_id']
            ):
                raise AppError(ErrorCode.CONFLICT, '网络配置已变化，请核对原任务')
        if not ResourceReservation.objects.filter(task=task, status='HELD').exists():
            raise AppError(ErrorCode.CONFLICT, '资源预留已结束，禁止重放硬件操作')
        task.payload['execution_started'] = True
        task.save(update_fields=['payload', 'updated_at'])
        Instance.objects.filter(pk=instance.pk).update(operation_status='PREPARING')
        result = AgentClient(instance.node.endpoint).domain_hardware(
            instance.libvirt_domain_name,
            change,
            storage_pool=instance.storage_pool.name if instance.storage_pool_id else '',
        )
        if not verify_result(result, change):
            raise AppError(ErrorCode.OPERATION_FAILED, '节点未确认目标硬件，保留预留以便核对')
        with transaction.atomic():
            instance = Instance.objects.select_for_update().get(pk=instance.pk)
            config = dict(instance.creation_config or {})
            op = change['operation']
            if op == 'compute':
                instance.vcpu = change['vcpu']
                instance.memory_mib = change['memory_mib']
                config['hardware'] = {
                    **config.get('hardware', {}),
                    'sockets': 1,
                    'cores': instance.vcpu,
                    'threads': 1,
                }
            elif op.startswith('disk-'):
                disk = instance.disks.select_for_update().get(pk=meta['disk_id'])
                disk.status = 'DETACHED' if op == 'disk-detach' else 'READY'
                disk.is_orphan = op == 'disk-detach'
                disk.size_gib = change['size_gib']
                disk.target_dev = change['target']
                disk.virtual_size_bytes = change['size_gib'] * GIB
                disk.save(
                    update_fields=[
                        'status',
                        'is_orphan',
                        'size_gib',
                        'virtual_size_bytes',
                        'target_dev',
                        'updated_at',
                    ]
                )
                if disk.role == 'SYSTEM':
                    instance.disk_gib = disk.size_gib
                config['data_disks'] = list(
                    instance.disks.filter(role='DATA', status='READY').values_list(
                        'size_gib', flat=True
                    )
                )
            elif op in {'cdrom-set', 'cdrom-remove'}:
                config['installation_media'] = meta.get('image_id') if op == 'cdrom-set' else None
            elif op == 'nic-add':
                InstanceNIC.objects.get_or_create(
                    instance=instance,
                    mac=change['mac'],
                    defaults={'network_id': meta['network_id'], 'device_id': meta['device_id']},
                )
            else:
                InstanceNIC.objects.filter(instance=instance, mac=change['mac']).delete()
                if config.get('primary_mac') == change['mac']:
                    config['primary_mac'] = ''
                    instance.network_name = ''
                if not result.get('nics'):
                    instance.network_name = ''
            config['hardware_inventory'] = result
            instance.creation_config = config
            instance.operation_status = 'SUCCEEDED'
            instance.last_error_code = instance.last_error_message = ''
            instance.save(
                update_fields=[
                    'vcpu',
                    'memory_mib',
                    'disk_gib',
                    'network_name',
                    'creation_config',
                    'operation_status',
                    'last_error_code',
                    'last_error_message',
                    'updated_at',
                ]
            )
            ResourceReservation.objects.filter(task=task).update(status='COMMITTED')
        return {
            'instance_id': instance.pk,
            'operation': change['operation'],
            'configured': result,
            'requires_guest_configuration': True,
        }
    except Exception as exc:
        Instance.objects.filter(pk=instance.pk).update(
            operation_status='FAILED',
            last_error_code=getattr(exc, 'code', ErrorCode.OPERATION_FAILED),
            last_error_message=f'{exc}；请核对实际硬件并重试原任务，资源预留暂保留',
        )
        raise
