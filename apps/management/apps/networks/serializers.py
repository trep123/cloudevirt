"""网络序列化器。"""

import ipaddress

from rest_framework import serializers

from apps.networks.models import Network


class NetworkSerializer(serializers.ModelSerializer):
    """网络输出结构。"""

    is_usable = serializers.BooleanField(read_only=True)

    class Meta:
        model = Network
        fields = (
            'id',
            'name',
            'type',
            'bridge',
            'vlan_id',
            'is_default',
            'is_management',
            'subnet',
            'gateway',
            'dhcp_enabled',
            'dhcp_start',
            'dhcp_end',
            'dns_servers',
            'description',
            'is_usable',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('created_at', 'updated_at')

    def validate_name(self, value: str) -> str:
        """校验名称格式。"""
        if len(value) < 2 or len(value) > 64:
            raise serializers.ValidationError('名称长度必须在 2-64 之间')
        if not value.replace('-', '').replace('_', '').isalnum():
            raise serializers.ValidationError('名称只能包含字母、数字、连字符与下划线')
        return value

    def validate(self, attrs: dict) -> dict:
        """校验默认/管理网互斥，以及网桥类型必须填写桥接设备。"""
        if attrs.get('is_management', getattr(self.instance, 'is_management', False)) and attrs.get(
            'is_default', getattr(self.instance, 'is_default', False)
        ):
            raise serializers.ValidationError('管理网不能作为默认网络')
        network_type = attrs.get('type', getattr(self.instance, 'type', ''))
        bridge = attrs.get('bridge', getattr(self.instance, 'bridge', ''))
        if network_type in {'BRIDGE', 'OVS'} and not bridge:
            raise serializers.ValidationError('网桥类型必须填写桥接设备名称')
        vlan = attrs.get('vlan_id', getattr(self.instance, 'vlan_id', None))
        if vlan is not None and not 1 <= vlan <= 4094:
            raise serializers.ValidationError('VLAN ID 必须在 1–4094 之间')

        subnet_raw = (attrs.get('subnet', getattr(self.instance, 'subnet', '')) or '').strip()
        gateway = attrs.get('gateway', getattr(self.instance, 'gateway', None))
        dhcp_enabled = attrs.get('dhcp_enabled', getattr(self.instance, 'dhcp_enabled', False))
        dhcp_start = attrs.get('dhcp_start', getattr(self.instance, 'dhcp_start', None))
        dhcp_end = attrs.get('dhcp_end', getattr(self.instance, 'dhcp_end', None))
        dns_servers = (
            attrs.get('dns_servers', getattr(self.instance, 'dns_servers', '')) or ''
        ).strip()

        if not subnet_raw and (gateway or dhcp_enabled or dhcp_start or dhcp_end):
            raise serializers.ValidationError('配置网关或 DHCP 前必须填写子网 CIDR')

        network = None
        if subnet_raw:
            try:
                network = ipaddress.ip_network(subnet_raw, strict=False)
            except ValueError as exc:
                raise serializers.ValidationError(f'子网 CIDR 格式非法：{exc}') from exc
            others = Network.objects.filter(is_deleted=False).exclude(subnet='')
            if self.instance:
                others = others.exclude(pk=self.instance.pk)
            for existing in others.values_list('subnet', flat=True):
                try:
                    other = ipaddress.ip_network(existing, strict=False)
                except ValueError:
                    continue
                if other.version == network.version and network.overlaps(other):
                    raise serializers.ValidationError('子网与已登记的网络重叠')
            if 'subnet' in attrs:
                attrs['subnet'] = str(network)

        if network is not None and gateway:
            try:
                gateway_address = ipaddress.ip_address(gateway)
            except ValueError as exc:
                raise serializers.ValidationError('网关地址格式非法') from exc
            if gateway_address.version != network.version or gateway_address not in network:
                raise serializers.ValidationError('网关必须属于子网')
            if network.version == 4 and gateway_address in {
                network.network_address,
                network.broadcast_address,
            }:
                raise serializers.ValidationError('网关不能是网络地址或广播地址')

        if dhcp_enabled:
            if network is None:
                raise serializers.ValidationError('启用 DHCP 前必须填写子网 CIDR')
            if not dhcp_start or not dhcp_end:
                raise serializers.ValidationError('启用 DHCP 时必须填写地址池起止地址')
            try:
                start_address = ipaddress.ip_address(dhcp_start)
                end_address = ipaddress.ip_address(dhcp_end)
            except ValueError as exc:
                raise serializers.ValidationError('DHCP 地址池格式非法') from exc
            if start_address.version != network.version or end_address.version != network.version:
                raise serializers.ValidationError('DHCP 地址池必须与子网 IP 版本一致')
            if start_address not in network or end_address not in network:
                raise serializers.ValidationError('DHCP 地址池必须位于子网内')
            if int(start_address) > int(end_address):
                raise serializers.ValidationError('DHCP 起始地址不能大于结束地址')
            if gateway and int(start_address) <= int(ipaddress.ip_address(gateway)) <= int(
                end_address
            ):
                raise serializers.ValidationError('DHCP 地址池不能包含网关地址')
            if network.version == 4 and (
                start_address == network.network_address or end_address == network.broadcast_address
            ):
                raise serializers.ValidationError('DHCP 地址池不能包含网络地址或广播地址')

        if dns_servers:
            for item in dns_servers.split(','):
                value = item.strip()
                if not value:
                    continue
                try:
                    ipaddress.ip_address(value)
                except ValueError as exc:
                    raise serializers.ValidationError(f'DNS 服务器地址非法：{value}') from exc
        return attrs
