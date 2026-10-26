"""实例 API：列表、创建（异步）、详情。"""

from rest_framework import generics, status
from rest_framework.response import Response

from apps.audit.models import AuditAction
from apps.audit.services import record_audit
from apps.instances.models import Instance
from apps.instances.serializers import (
    InstanceCreateSerializer,
    InstanceSerializer,
    TaskReferenceSerializer,
)
from apps.instances.services import create_instance
from common.permissions import (
    CanCreateInstance,
    CanViewInstance,
    RequiresPasswordChange,
)


class InstanceListCreateView(generics.ListCreateAPIView):
    """实例列表与创建。"""

    permission_classes = [RequiresPasswordChange]
    queryset = Instance.objects.filter(is_deleted=False).select_related('node', 'image')

    def get_permissions(self):
        """按动作选择权限类。"""
        if self.request.method == 'POST':
            return [CanCreateInstance(), RequiresPasswordChange()]
        return [CanViewInstance(), RequiresPasswordChange()]

    def get_serializer_class(self):
        """写操作使用创建序列化器。"""
        if self.request.method == 'POST':
            return InstanceCreateSerializer
        return InstanceSerializer

    def create(self, request, *args, **kwargs) -> Response:
        """创建实例并返回 202 与任务引用。"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        instance, task = create_instance(
            user=request.user,
            name=data['name'],
            node=data['node'],
            image=data['image'],
            vcpu=data['vcpu'],
            memory_mib=data['memory_mib'],
            disk_gib=data['disk_gib'],
            network_name=data.get('network_name', ''),
            autostart=data.get('autostart', False),
            idempotency_key=request.headers.get('Idempotency-Key') or None,
        )
        record_audit(
            action=AuditAction.INSTANCE_CREATE,
            actor=request.user,
            target_type='instance',
            target_id=str(instance.pk),
            details={
                'name': instance.name,
                'node': instance.node_id,
                'image': instance.image_id,
                'vcpu': instance.vcpu,
                'memory_mib': instance.memory_mib,
                'disk_gib': instance.disk_gib,
            },
        )
        payload = {
            'instance': InstanceSerializer(instance).data,
            'task': TaskReferenceSerializer(
                {
                    'id': task.pk,
                    'status': task.status,
                    'status_url': f'/api/v1/tasks/{task.pk}',
                }
            ).data,
        }
        return Response(payload, status=status.HTTP_202_ACCEPTED)


class InstanceDetailView(generics.RetrieveAPIView):
    """实例详情。"""

    permission_classes = [CanViewInstance, RequiresPasswordChange]
    queryset = Instance.objects.filter(is_deleted=False).select_related('node', 'image')
    serializer_class = InstanceSerializer
