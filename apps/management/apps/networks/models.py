"""网络白名单模型。

MVP 只登记经管理员验证的 libvirt 网络或网桥；实例创建只允许接入白名单内且
非管理网的网络。
"""

import uuid

from django.db import models


class NetworkType(models.TextChoices):
    """网络类型。"""

    LIBVIRT_NETWORK = 'LIBVIRT_NETWORK', 'libvirt 网络'
    BRIDGE = 'BRIDGE', 'Linux 网桥'
    OVS = 'OVS', 'Open vSwitch 网桥'


class Network(models.Model):
    """白名单网络。"""

    name = models.CharField('名称', max_length=64, unique=True)
    node = models.ForeignKey('nodes.Node', on_delete=models.PROTECT, null=True, blank=True)
    managed = models.BooleanField(default=False)
    uplink = models.CharField(max_length=15, blank=True, default='')
    provisioning_status = models.CharField(max_length=16, default='READY')
    last_error = models.CharField(max_length=500, blank=True, default='')
    type = models.CharField(
        '类型', max_length=16, choices=NetworkType.choices, default=NetworkType.LIBVIRT_NETWORK
    )
    bridge = models.CharField('桥接设备', max_length=32, blank=True, default='')
    vlan_id = models.PositiveIntegerField('VLAN', null=True, blank=True)
    is_default = models.BooleanField('默认网络', default=False)
    is_management = models.BooleanField('管理网（禁止接入）', default=False)
    subnet = models.CharField('子网 CIDR', max_length=64, blank=True, default='')
    gateway = models.GenericIPAddressField('网关', null=True, blank=True)
    dhcp_enabled = models.BooleanField('启用 DHCP', default=False)
    dhcp_start = models.GenericIPAddressField('DHCP 起始地址', null=True, blank=True)
    dhcp_end = models.GenericIPAddressField('DHCP 结束地址', null=True, blank=True)
    dns_servers = models.CharField('DNS 服务器', max_length=255, blank=True, default='')
    description = models.CharField('说明', max_length=200, blank=True, default='')
    is_deleted = models.BooleanField('已删除', default=False)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '网络'
        verbose_name_plural = '网络'
        ordering = ['name']
        permissions = [('manage_network', '可以维护网络白名单')]

    def __str__(self) -> str:
        """返回可读标识。"""
        return f'{self.name} ({self.type})'

    @property
    def is_usable(self) -> bool:
        """是否允许实例接入。"""
        return (
            not self.is_deleted and not self.is_management and self.provisioning_status == 'READY'
        )


class IPPool(models.Model):
    network = models.ForeignKey(Network, on_delete=models.PROTECT, related_name='ip_pools')
    name = models.CharField(max_length=64)
    first_ip = models.GenericIPAddressField(protocol='IPv4')
    last_ip = models.GenericIPAddressField(protocol='IPv4')
    gateway = models.GenericIPAddressField(protocol='IPv4')
    dns_servers = models.JSONField(default=list)
    enabled = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['network', 'name'],
                condition=models.Q(is_deleted=False),
                name='unique_live_ip_pool_name',
            )
        ]

    def __str__(self):
        return self.name


class InstanceNIC(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    instance = models.ForeignKey(
        'instances.Instance', on_delete=models.CASCADE, related_name='network_interfaces'
    )
    network = models.ForeignKey(
        Network, on_delete=models.PROTECT, related_name='instance_interfaces'
    )
    device_id = models.CharField(max_length=16)
    mac = models.CharField(max_length=17, unique=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['instance', 'device_id'], name='unique_instance_nic_device'
            )
        ]

    def __str__(self):
        return f'{self.instance_id}:{self.device_id}'


class IPLease(models.Model):
    pool = models.ForeignKey(IPPool, on_delete=models.PROTECT, related_name='leases')
    nic = models.OneToOneField(InstanceNIC, on_delete=models.PROTECT, related_name='ip_lease')
    network = models.ForeignKey(Network, on_delete=models.PROTECT)
    address = models.GenericIPAddressField(protocol='IPv4')
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['network', 'address'],
                condition=models.Q(active=True),
                name='unique_active_network_ip',
            )
        ]

    def __str__(self):
        return self.address
