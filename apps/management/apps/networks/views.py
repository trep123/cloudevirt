"""网络 API：白名单列表与维护。"""

from rest_framework import generics

from apps.audit.models import AuditAction
from apps.audit.services import record_audit
from apps.networks.models import Network
from apps.networks.serializers import NetworkSerializer
from common.permissions import CanManageNetwork, CanViewNetwork, RequiresPasswordChange


class NetworkListCreateView(generics.ListCreateAPIView):
    """网络列表与登记。"""

    permission_classes = [RequiresPasswordChange]
    queryset = Network.objects.filter(is_deleted=False)
    serializer_class = NetworkSerializer

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

    def perform_update(self, serializer) -> None:
        """保存变更并写审计。"""
        network = serializer.save()
        record_audit(
            action=AuditAction.NETWORK_UPDATE,
            actor=self.request.user,
            target_type='network',
            target_id=str(network.pk),
            details={'name': network.name, 'is_management': network.is_management},
        )

    def perform_destroy(self, instance) -> None:
        """软删除网络，并提示调用方检查实例引用。"""
        instance.is_deleted = True
        instance.save(update_fields=['is_deleted', 'updated_at'])
        record_audit(
            action=AuditAction.NETWORK_DELETE,
            actor=self.request.user,
            target_type='network',
            target_id=str(instance.pk),
            details={'name': instance.name},
        )
