import ipaddress

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.administration import require_admin
from apps.accounts.roles import is_admin
from apps.audit.services import record_audit
from apps.networks.models import IPLease, IPPool, Network
from common.errors import AppError, ErrorCode
from common.permissions import CanViewNetwork, RequiresPasswordChange


class PoolInput(serializers.ModelSerializer):
    class Meta:
        model = IPPool
        fields = [
            'id',
            'name',
            'network',
            'first_ip',
            'last_ip',
            'gateway',
            'dns_servers',
            'enabled',
            'revision',
        ]
        read_only_fields = ['id']
        validators = []

    def to_internal_value(self, data):
        if set(data) - set(self.fields):
            raise serializers.ValidationError('存在未知地址池字段')
        return super().to_internal_value(data)

    def validate(self, data):
        network = data.get('network', getattr(self.instance, 'network', None))
        if not network or not network.is_usable:
            raise serializers.ValidationError({'network': '网络不可用'})
        try:
            subnet = ipaddress.ip_network(network.subnet, strict=True)
            first = ipaddress.ip_address(
                data.get('first_ip', getattr(self.instance, 'first_ip', ''))
            )
            last = ipaddress.ip_address(data.get('last_ip', getattr(self.instance, 'last_ip', '')))
            gateway = ipaddress.ip_address(
                data.get('gateway', getattr(self.instance, 'gateway', ''))
            )
        except ValueError:
            raise serializers.ValidationError(
                '网络必须登记有效 IPv4 子网，地址池需填写合法地址'
            ) from None
        if (
            subnet.version != 4
            or any(ip not in subnet for ip in [first, last, gateway])
            or not subnet.network_address < first <= last < subnet.broadcast_address
            or not subnet.network_address < gateway < subnet.broadcast_address
            or first <= gateway <= last
            or int(last) - int(first) > 4095
        ):
            raise serializers.ValidationError(
                '地址池必须是子网内最多 4096 个可用 IPv4 地址，不能包含网关'
            )
        if network.dhcp_enabled and network.dhcp_start and network.dhcp_end:
            low = ipaddress.ip_address(network.dhcp_start)
            high = ipaddress.ip_address(network.dhcp_end)
            if first <= high and last >= low:
                raise serializers.ValidationError('静态地址池与 DHCP 地址范围重叠')
        existing = IPPool.objects.filter(network=network, is_deleted=False)
        if self.instance:
            existing = existing.exclude(pk=self.instance.pk)
        for pool in existing:
            if first <= ipaddress.ip_address(pool.last_ip) and last >= ipaddress.ip_address(
                pool.first_ip
            ):
                raise serializers.ValidationError('与已有静态地址池重叠')
            if pool.name == data.get('name'):
                raise serializers.ValidationError({'name': '同网络下地址池名称重复'})
        dns = data.get('dns_servers', getattr(self.instance, 'dns_servers', []))
        if not isinstance(dns, list) or len(dns) > 4:
            raise serializers.ValidationError({'dns_servers': '最多 4 个 DNS 地址'})
        try:
            for address in dns:
                ipaddress.ip_address(address)
        except ValueError, TypeError:
            raise serializers.ValidationError({'dns_servers': 'DNS 地址格式无效'}) from None
        if (
            self.instance
            and self.instance.leases.filter(active=True).exists()
            and any(
                key not in ['enabled', 'revision'] and value != getattr(self.instance, key)
                for key, value in data.items()
            )
        ):
            raise serializers.ValidationError('地址池仍有有效租约，不能修改地址配置')
        return data


class IPPoolsView(APIView):
    permission_classes = [CanViewNetwork, RequiresPasswordChange]

    def get(self, request):
        query = (
            IPPool.objects.filter(
                is_deleted=False, network__is_deleted=False, network__is_management=False
            )
            .select_related('network')
            .order_by('pk')
        )
        if not is_admin(request.user):
            query = query.filter(enabled=True)
        network = request.query_params.get('network')
        if network:
            if not network.isdigit():
                raise serializers.ValidationError('网络 ID 无效')
            query = query.filter(network_id=int(network))
        values = PoolInput(query, many=True).data
        return Response({'results': values})

    @transaction.atomic
    def post(self, request):
        require_admin(request.user, 'networks.manage_network')
        serializer = PoolInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        Network.objects.select_for_update().get(pk=serializer.validated_data['network'].pk)
        serializer = PoolInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        pool = serializer.save(revision=1)
        record_audit(
            action='IP_POOL_CREATE',
            actor=request.user,
            target_type='ip_pool',
            target_id=str(pool.pk),
            details={'network': pool.network_id, 'name': pool.name},
        )
        return Response(PoolInput(pool).data, status=201)


class IPPoolDetailView(APIView):
    permission_classes = [RequiresPasswordChange]

    @transaction.atomic
    def patch(self, request, pk):
        require_admin(request.user, 'networks.manage_network')
        initial = get_object_or_404(IPPool, pk=pk, is_deleted=False)
        Network.objects.select_for_update().get(pk=initial.network_id)
        pool = IPPool.objects.select_for_update().get(pk=pk)
        if request.data.get('revision') != pool.revision:
            raise AppError(ErrorCode.CONFLICT, '地址池已变化，请刷新')
        if 'network' in request.data and request.data['network'] != pool.network_id:
            raise serializers.ValidationError('地址池所属网络不可修改')
        serializer = PoolInput(pool, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(revision=pool.revision + 1)
        record_audit(
            action='IP_POOL_UPDATE',
            actor=request.user,
            target_type='ip_pool',
            target_id=str(pk),
            details={'enabled': pool.enabled, 'revision': pool.revision},
        )
        return Response(serializer.data)

    @transaction.atomic
    def delete(self, request, pk):
        require_admin(request.user, 'networks.manage_network')
        initial = get_object_or_404(IPPool, pk=pk, is_deleted=False)
        Network.objects.select_for_update().get(pk=initial.network_id)
        pool = IPPool.objects.select_for_update().get(pk=pk)
        if pool.leases.filter(active=True).exists():
            raise AppError(ErrorCode.CONFLICT, '地址池仍有有效租约')
        pool.enabled = False
        pool.is_deleted = True
        pool.revision += 1
        pool.save()
        record_audit(
            action='IP_POOL_DELETE',
            actor=request.user,
            target_type='ip_pool',
            target_id=str(pk),
            details={},
        )
        return Response(status=204)


def allocate_address(pool, nic, requested=None):
    if pool.is_deleted or not pool.enabled or pool.network_id != nic.network_id:
        raise AppError(ErrorCode.CONFLICT, '地址池不可用或不属于所选网络')
    # Caller holds the pool row lock; uniqueness also enforced by PostgreSQL.
    first = int(ipaddress.ip_address(pool.first_ip))
    last = int(ipaddress.ip_address(pool.last_ip))
    used = set(pool.leases.filter(active=True).values_list('address', flat=True))
    if requested:
        address = ipaddress.ip_address(requested)
        if address.version != 4 or not first <= int(address) <= last or str(address) in used:
            raise AppError(ErrorCode.CONFLICT, '静态 IP 不在地址池内或已被占用')
        selected = str(address)
    else:
        selected = next(
            (
                str(ipaddress.ip_address(value))
                for value in range(first, last + 1)
                if str(ipaddress.ip_address(value)) not in used
            ),
            None,
        )
        if not selected:
            raise AppError(ErrorCode.INSUFFICIENT_RESOURCE, '静态地址池已用完')
    return IPLease.objects.create(pool=pool, nic=nic, network=pool.network, address=selected)
