import ipaddress
import secrets

from django.db import IntegrityError, transaction

from apps.networks.addresses import allocate_address
from apps.networks.models import InstanceNIC, IPPool
from common.errors import AppError, ErrorCode


def provision_interfaces(instance, primary, additional, static):
    pools = {
        pool.pk: pool
        for pool in IPPool.objects.select_for_update()
        .filter(pk__in=sorted({value['pool'] for value in static.values()}))
        .order_by('pk')
    }
    networks = ([primary] if primary else []) + additional
    if set(static) - {network.name for network in networks}:
        raise AppError(ErrorCode.INVALID_ARGUMENT, '静态配置引用了未选择的网络')
    specs = []
    guests = []
    explicit_default = any(value.get('default_route') is True for value in static.values())
    for index, network in enumerate(networks):
        for attempt in range(16):
            mac = '02:' + ':'.join(f'{byte:02x}' for byte in secrets.token_bytes(5))
            try:
                with transaction.atomic():
                    nic = InstanceNIC.objects.create(
                        instance=instance, network=network, device_id=f'nic{index}', mac=mac
                    )
                break
            except IntegrityError:
                if attempt == 15:
                    raise AppError(ErrorCode.CONFLICT, '无法分配唯一网卡地址') from None
        specs.append(
            {
                'network': network.name,
                'network_type': network.type,
                'network_bridge': network.bridge,
                'vlan_id': network.vlan_id or 0,
                'mac': mac,
            }
        )
        requested = static.get(network.name)
        default = (
            requested.get('default_route', False if explicit_default else index == 0)
            if requested
            else (not explicit_default and index == 0)
        )
        guest = {'mac': mac, 'name': f'cvnet{index}', 'dhcp4': True, 'default_route': default}
        if requested:
            pool = pools.get(requested['pool'])
            if pool is None:
                raise AppError(ErrorCode.CONFLICT, '地址池不存在')
            lease = allocate_address(pool, nic, requested.get('address'))
            guest.update(
                dhcp4=False,
                address=f'{lease.address}/{ipaddress.ip_network(network.subnet).prefixlen}',
                gateway=pool.gateway,
                dns=pool.dns_servers,
            )
        guests.append(guest)
    instance.creation_config.update(
        primary_mac=specs[0]['mac'] if primary and specs else '',
        network_specs=specs[1:] if primary else specs,
        guest_networks=guests,
    )
    instance.save(update_fields=['creation_config'])
