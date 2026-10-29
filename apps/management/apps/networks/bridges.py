"""Task-backed physical bridge provisioning; only the restricted node helper mutates links."""

import hashlib

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.administration import require_admin
from apps.audit.services import record_audit
from apps.networks.models import Network
from apps.networks.serializers import NetworkSerializer
from apps.nodes.client import AgentClient
from apps.nodes.models import Node
from apps.tasks.models import ACTIVE_STATUSES, RETRYABLE_ERROR_CODES, Task
from apps.tasks.services import enqueue
from common.errors import AppError, ErrorCode
from common.permissions import CanManageNetwork, RequiresPasswordChange


class BridgeInput(serializers.Serializer):
    name = serializers.RegexField(r'^[A-Za-z0-9][A-Za-z0-9_-]{1,63}$')
    node = serializers.IntegerField(min_value=1)
    type = serializers.ChoiceField(choices=['BRIDGE', 'OVS'])
    bridge = serializers.RegexField(r'^[A-Za-z][A-Za-z0-9_-]{0,14}$')
    uplink = serializers.RegexField(r'^[A-Za-z][A-Za-z0-9_-]{0,14}$')
    description = serializers.CharField(max_length=200, allow_blank=True, default='')


def response(task):
    network = get_object_or_404(Network, pk=task.resource_id)
    return Response(
        {
            'task_id': str(task.pk),
            'status': task.status,
            'network': NetworkSerializer(network).data,
        },
        status=202,
    )


class PhysicalInterfacesView(APIView):
    permission_classes = [CanManageNetwork, RequiresPasswordChange]

    def get(self, request, node_id):
        require_admin(request.user, 'networks.manage_network')
        node = get_object_or_404(Node, pk=node_id, is_deleted=False)
        if not node.is_schedulable:
            raise AppError(ErrorCode.NODE_OFFLINE)
        result = Response(AgentClient(node.endpoint).get_json('/api/v1/node/physical-interfaces'))
        result['Cache-Control'] = 'no-store'
        return result


class BridgeCreateView(APIView):
    permission_classes = [CanManageNetwork, RequiresPasswordChange]

    @transaction.atomic
    def post(self, request):
        require_admin(request.user, 'networks.manage_network')
        if set(request.data) - set(BridgeInput().fields):
            raise serializers.ValidationError('存在未知网桥配置字段')
        serializer = BridgeInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        key = request.headers.get('Idempotency-Key', '')
        if not key or len(key) > 128:
            raise serializers.ValidationError('必须提供 Idempotency-Key（不超过 128 字符）')
        digest = hashlib.sha256(f'bridge:{request.user.pk}:{key}'.encode()).hexdigest()
        node = get_object_or_404(
            Node.objects.select_for_update(), pk=data['node'], is_deleted=False
        )
        previous = Task.objects.filter(idempotency_key=digest, requested_by=request.user).first()
        if previous:
            if previous.type != 'NETWORK_BRIDGE_CREATE' or previous.payload != data:
                raise AppError(ErrorCode.CONFLICT, '幂等键已用于不同请求')
            return response(previous)
        if not node.is_schedulable:
            raise AppError(ErrorCode.NODE_OFFLINE)
        if Network.objects.filter(name=data['name']).exists():
            raise AppError(ErrorCode.CONFLICT, '网络名称已存在')
        if (
            Network.objects.filter(node=node, managed=True, is_deleted=False)
            .filter(Q(bridge=data['bridge']) | Q(uplink=data['uplink']))
            .exists()
        ):
            raise AppError(ErrorCode.CONFLICT, '网桥名称或物理网卡已被预留，请核对现有任务')
        interfaces = (
            AgentClient(node.endpoint)
            .get_json('/api/v1/node/physical-interfaces')
            .get('interfaces', [])
        )
        if not any(
            i.get('name') == data['uplink'] and i.get('eligible') is True for i in interfaces
        ):
            raise AppError(ErrorCode.CONFLICT, '物理网卡不可用：管理地址、路由及已占用接口禁止桥接')
        try:
            with transaction.atomic():
                network = Network.objects.create(
                    name=data['name'],
                    node=node,
                    type=data['type'],
                    bridge=data['bridge'],
                    uplink=data['uplink'],
                    description=data['description'],
                    managed=True,
                    provisioning_status='PENDING',
                )
        except IntegrityError as exc:
            raise AppError(ErrorCode.CONFLICT, '网络名称或接口已被其他请求占用') from exc
        task = enqueue(
            task_type='NETWORK_BRIDGE_CREATE',
            resource_type='network',
            resource_id=str(network.pk),
            requested_by=request.user,
            payload=data,
            idempotency_key=digest,
        )
        record_audit(
            action='NETWORK_BRIDGE_CREATE',
            actor=request.user,
            target_type='network',
            target_id=str(network.pk),
            task_id=str(task.pk),
            details=data,
        )
        return response(task)


class BridgeRetryView(APIView):
    permission_classes = [CanManageNetwork, RequiresPasswordChange]

    @transaction.atomic
    def post(self, request, pk):
        require_admin(request.user, 'networks.manage_network')
        network = get_object_or_404(
            Network.objects.select_for_update(), pk=pk, is_deleted=False, managed=True
        )
        active = Task.objects.filter(
            resource_type='network', resource_id=str(pk), status__in=list(ACTIVE_STATUSES)
        ).first()
        if active:
            return response(active)
        if network.provisioning_status == 'READY':
            raise AppError(ErrorCode.CONFLICT, '网桥已经就绪')
        payload = {
            k: getattr(network, k) for k in ['name', 'type', 'bridge', 'uplink', 'description']
        }
        payload['node'] = network.node_id
        task = enqueue(
            task_type='NETWORK_BRIDGE_CREATE',
            resource_type='network',
            resource_id=str(pk),
            requested_by=request.user,
            payload=payload,
        )
        network.provisioning_status = 'PENDING'
        network.last_error = ''
        network.save(update_fields=['provisioning_status', 'last_error', 'updated_at'])
        record_audit(
            action='NETWORK_BRIDGE_RETRY',
            actor=request.user,
            target_type='network',
            target_id=str(pk),
            task_id=str(task.pk),
        )
        return response(task)


def execute_bridge(task):
    network = get_object_or_404(
        Network.objects.select_related('node'), pk=task.resource_id, managed=True, is_deleted=False
    )
    Network.objects.filter(pk=network.pk).update(
        provisioning_status='CREATING', last_error='', updated_at=timezone.now()
    )
    try:
        if task.requested_by is None:
            raise AppError(ErrorCode.PERMISSION_DENIED)
        require_admin(task.requested_by, 'networks.manage_network')
        if not network.node.is_schedulable:
            raise AppError(ErrorCode.NODE_OFFLINE)
        expected = {k: getattr(network, k) for k in ['type', 'bridge', 'uplink']}
        result = AgentClient(network.node.endpoint).request_json(
            '/api/v1/node/bridges', 'POST', expected
        )
        if (
            not isinstance(result, dict)
            or result.get('verified') is not True
            or any(result.get(k) != v for k, v in expected.items())
        ):
            raise AppError(ErrorCode.CONFLICT, '节点未确认网桥及物理端口，保留配置以供核对')
    except AppError as exc:
        status = (
            'PENDING'
            if exc.code in RETRYABLE_ERROR_CODES and task.attempt_count < task.max_attempts
            else 'FAILED'
        )
        Network.objects.filter(pk=network.pk).update(
            provisioning_status=status, last_error=exc.message[:500], updated_at=timezone.now()
        )
        raise
    Network.objects.filter(pk=network.pk).update(
        provisioning_status='READY', last_error='', updated_at=timezone.now()
    )
    record_audit(
        action='NETWORK_BRIDGE_READY',
        actor=task.requested_by,
        target_type='network',
        target_id=str(network.pk),
        task_id=str(task.pk),
        details=result,
    )
    return result
