"""节点 API：列表、注册、详情、主动刷新。"""

from rest_framework import generics
from rest_framework.response import Response

from apps.audit.models import AuditAction
from apps.audit.services import record_audit
from apps.nodes.models import Node
from apps.nodes.serializers import NodeCreateSerializer, NodeSerializer, NodeUpdateSerializer
from apps.nodes.services import refresh_node
from common.permissions import (
    CanOperateNode,
    CanRefreshNode,
    CanRegisterNode,
    RequiresPasswordChange,
)


class NodeListCreateView(generics.ListCreateAPIView):
    """节点列表与注册。"""

    permission_classes = [RequiresPasswordChange]
    queryset = Node.objects.filter(is_deleted=False)

    def get_permissions(self):
        """按动作选择权限类。"""
        if self.request.method == 'POST':
            return [CanRegisterNode(), RequiresPasswordChange()]
        return [CanOperateNode(), RequiresPasswordChange()]

    def get_serializer_class(self):
        """写操作使用注册序列化器。"""
        if self.request.method == 'POST':
            return NodeCreateSerializer
        return NodeSerializer

    def perform_create(self, serializer) -> None:
        """保存节点并写审计。"""
        node = serializer.save()
        record_audit(
            action=AuditAction.NODE_REGISTER,
            actor=self.request.user,
            target_type='node',
            target_id=str(node.pk),
            details={'name': node.name, 'endpoint': node.endpoint},
        )


class NodeDetailView(generics.RetrieveUpdateDestroyAPIView):
    """节点详情与更新（DELETE 语义为注销）。"""

    permission_classes = [CanOperateNode, RequiresPasswordChange]
    queryset = Node.objects.filter(is_deleted=False)

    def get_permissions(self):
        """写操作要求管理员权限。"""
        if self.request.method == 'GET':
            return [CanOperateNode(), RequiresPasswordChange()]
        return [CanRegisterNode(), RequiresPasswordChange()]

    def get_serializer_class(self):
        """读操作返回完整信息。"""
        if self.request.method == 'GET':
            return NodeSerializer
        return NodeUpdateSerializer

    def perform_update(self, serializer) -> None:
        """保存变更并写审计。"""
        node = serializer.save()
        record_audit(
            action=AuditAction.NODE_UPDATE,
            actor=self.request.user,
            target_type='node',
            target_id=str(node.pk),
            details={'name': node.name, 'status': node.status},
        )

    def perform_destroy(self, instance) -> None:
        """注销节点（软删除），已有实例的节点由后续模块校验引用。"""
        instance.is_deleted = True
        instance.save(update_fields=['is_deleted', 'updated_at'])
        record_audit(
            action=AuditAction.NODE_UPDATE,
            actor=self.request.user,
            target_type='node',
            target_id=str(instance.pk),
            details={'name': instance.name, 'is_deleted': True},
        )


class NodeRefreshView(generics.GenericAPIView):
    """主动刷新节点资源（同步调用，受超时约束）。"""

    permission_classes = [CanRefreshNode, RequiresPasswordChange]
    queryset = Node.objects.filter(is_deleted=False)
    serializer_class = NodeSerializer

    def post(self, request, pk: int) -> Response:
        """触发一次采集并返回最新节点信息。"""
        node = self.get_object()
        refresh_node(node)
        record_audit(
            action=AuditAction.NODE_REFRESH,
            actor=request.user,
            target_type='node',
            target_id=str(node.pk),
            details={'status': node.status},
        )
        return Response(NodeSerializer(node).data)
