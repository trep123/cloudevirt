"""网络 API：白名单列表与维护。"""

from django.db import transaction
from rest_framework import generics

from apps.audit.models import AuditAction
from apps.audit.services import record_audit
from apps.instances.models import Instance
from apps.networks.models import Network
from apps.networks.scope import networks_for
from apps.networks.serializers import NetworkSerializer
from common.errors import AppError, ErrorCode
from common.permissions import CanManageNetwork, CanViewNetwork, RequiresPasswordChange


class NetworkListCreateView(generics.ListCreateAPIView):
    """网络列表与登记。"""

    permission_classes = [RequiresPasswordChange]
    queryset = Network.objects.filter(is_deleted=False)
    serializer_class = NetworkSerializer

    def get_queryset(self):
        return networks_for(self.request.user)

    def get_permissions(self):
        """按动作选择权限类。"""
        if self.request.method == 'POST':
            return [CanManageNetwork(), RequiresPasswordChange()]
        return [CanViewNetwork(), RequiresPasswordChange()]

    def perform_create(self, serializer) -> None:
        """保存网络并写审计。"""
        network = serializer.save()
        record_audit(
            action=AuditAction.NETWORK_CREATE,
            actor=self.request.user,
            target_type='network',
            target_id=str(network.pk),
            details={'name': network.name, 'is_management': network.is_management},
        )


class NetworkDetailView(generics.RetrieveUpdateDestroyAPIView):
    """网络详情、更新与删除。"""

    permission_classes = [CanManageNetwork, RequiresPasswordChange]
    queryset = Network.objects.filter(is_deleted=False)
    serializer_class = NetworkSerializer

    @transaction.atomic
    def perform_update(self, serializer) -> None:
        """保存变更并写审计。"""
        serializer.instance = Network.objects.select_for_update().get(pk=serializer.instance.pk)
        if serializer.instance.managed and any(
            key in serializer.validated_data
            and serializer.validated_data[key] != getattr(serializer.instance, key)
            for key in ['name', 'type', 'bridge', 'is_management']
        ):
            raise AppError(ErrorCode.CONFLICT, '托管网桥连接属性不可通过登记接口修改')
        from apps.networks.models import InstanceNIC, IPPool

        address_fields = {
            'subnet',
            'gateway',
            'dhcp_enabled',
            'dhcp_start',
            'dhcp_end',
            'dns_servers',
        }
        changed = {
            key
            for key, value in serializer.validated_data.items()
            if value != getattr(serializer.instance, key)
        }
        if (
            changed & address_fields
            and IPPool.objects.filter(network=serializer.instance, is_deleted=False).exists()
        ):
            raise AppError(ErrorCode.CONFLICT, '网络存在静态地址池，请先解除租约并移除地址池')
        if (
            changed & {'name', 'type', 'bridge', 'vlan_id', 'is_management'}
            and InstanceNIC.objects.filter(
                network=serializer.instance, instance__is_deleted=False
            ).exists()
        ):
            raise AppError(ErrorCode.CONFLICT, '网络仍被虚拟机网卡引用')
        immutable = {'name', 'type', 'bridge', 'vlan_id', 'subnet', 'gateway'}
        if Instance.objects.filter(
            network_name=serializer.instance.name, is_deleted=False
        ).exists():
            changed = [
                key
                for key in immutable
                if key in serializer.validated_data
                and serializer.validated_data[key] != getattr(serializer.instance, key)
            ]
            if changed:
                raise AppError(
                    ErrorCode.CONFLICT,
                    '网络被实例引用，不能直接修改连接配置',
                    details={'fields': changed},
                )
        network = serializer.save()
        record_audit(
            action=AuditAction.NETWORK_UPDATE,
            actor=self.request.user,
            target_type='network',
            target_id=str(network.pk),
            details={'name': network.name, 'is_management': network.is_management},
        )

    @transaction.atomic
    def perform_destroy(self, instance) -> None:
        """软删除网络，并提示调用方检查实例引用。"""
        instance = Network.objects.select_for_update().get(pk=instance.pk)
        if instance.is_management:
            raise AppError(ErrorCode.CONFLICT, '管理网络禁止删除')
        from apps.networks.models import InstanceNIC, IPPool

        if (
            IPPool.objects.filter(network=instance, is_deleted=False).exists()
            or InstanceNIC.objects.filter(network=instance, instance__is_deleted=False).exists()
        ):
            raise AppError(ErrorCode.CONFLICT, '网络仍被地址池或虚拟机网卡引用')
        if Instance.objects.filter(network_name=instance.name, is_deleted=False).exists():
            raise AppError(ErrorCode.CONFLICT, '网络仍被虚拟机引用，不能删除')
        if instance.managed:
            from apps.nodes.client import AgentClient
            from apps.nodes.models import Node

            node = Node.objects.select_for_update().get(pk=instance.node_id)
            if not node.is_schedulable:
                raise AppError(ErrorCode.NODE_OFFLINE)
            if instance.provisioning_status in ['PENDING', 'CREATING']:
                raise AppError(ErrorCode.CONFLICT, '网桥创建任务尚未结束')
            result = AgentClient(node.endpoint).request_json(
                '/api/v1/node/bridges',
                'DELETE',
                {key: getattr(instance, key) for key in ['type', 'bridge', 'uplink']},
            )
            if result.get('deleted') is not True:
                raise AppError(ErrorCode.CONFLICT, '节点未确认网桥已删除')
        instance.is_deleted = True
        instance.save(update_fields=['is_deleted', 'updated_at'])
        record_audit(
            action=AuditAction.NETWORK_DELETE,
            actor=self.request.user,
            target_type='network',
            target_id=str(instance.pk),
            details={'name': instance.name},
        )
