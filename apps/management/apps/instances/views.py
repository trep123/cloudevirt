"""实例 API：列表、创建（异步）、详情。"""

from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import AuditAction
from apps.audit.services import record_audit
from apps.instances.actions import request_delete, start_action
from apps.instances.models import Instance
from apps.instances.serializers import (
    DiskSerializer,
    InstanceCreateSerializer,
    InstanceSerializer,
    TaskReferenceSerializer,
)
from apps.instances.services import create_instance
from apps.nodes.client import AgentClient
from common.errors import AppError, ErrorCode
from common.permissions import (
    CanCreateInstance,
    CanViewInstance,
    RequiresPasswordChange,
    check_permission,
)
from common.scope import InstanceScopeMixin, instances_for


class InstanceListCreateView(InstanceScopeMixin, generics.ListCreateAPIView):
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
            start_after_create=data.get('start_after_create', True),
            template=data.get('template'),
            template_version=data.get('template_version'),
            existing_system_disk=data.get('existing_system_disk'),
            existing_system_file=data.get('existing_system_file'),
            clone_mode=data.get('clone_mode'),
            data_disks=data.get('data_disks', []),
            additional_networks=data.get('additional_networks', []),
            hardware=data.get('hardware', {}),
            initialization=data.get('initialization'),
            static_networks=data.get('static_networks', {}),
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


class InstanceDetailView(InstanceScopeMixin, generics.RetrieveDestroyAPIView):
    """实例详情与删除（DELETE 语义见 request_delete）。"""

    permission_classes = [IsAuthenticated, RequiresPasswordChange]
    queryset = Instance.objects.filter(is_deleted=False).select_related('node', 'image')
    serializer_class = InstanceSerializer

    def get_permissions(self):
        """读操作要求查看权限；删除在方法内做细粒度校验。"""
        if self.request.method == 'GET':
            return [CanViewInstance(), RequiresPasswordChange()]
        return [IsAuthenticated(), RequiresPasswordChange()]

    def delete(self, request, *args, **kwargs) -> Response:
        """删除实例：purge_disk 显式声明是否删除磁盘。"""
        instance = self.get_object()
        check_permission(
            request.user,
            'instances.delete_instance',
            target_type='instance',
            target_id=str(instance.pk),
        )
        purge_disk = str(request.query_params.get('purge_disk', 'false')).lower() in {
            '1',
            'true',
            'yes',
        }
        if purge_disk:
            check_permission(
                request.user,
                'instances.delete_disk_instance',
                target_type='instance',
                target_id=str(instance.pk),
            )

        task = request_delete(instance, request.user, purge_disk=purge_disk)
        record_audit(
            action=AuditAction.INSTANCE_DELETE,
            actor=request.user,
            target_type='instance',
            target_id=str(instance.pk),
            task_id=str(task.pk),
            details={'name': instance.name, 'purge_disk': purge_disk},
        )
        return Response(
            {
                'task': {
                    'id': str(task.pk),
                    'status': task.status,
                    'status_url': f'/api/v1/tasks/{task.pk}',
                }
            },
            status=status.HTTP_202_ACCEPTED,
        )


ACTION_PERMISSIONS = {
    'start': 'instances.start_instance',
    'shutdown': 'instances.shutdown_instance',
    'force-stop': 'instances.force_stop_instance',
    'reboot': 'instances.reboot_instance',
}

ACTION_AUDIT = {
    'start': AuditAction.INSTANCE_START,
    'shutdown': AuditAction.INSTANCE_SHUTDOWN,
    'force-stop': AuditAction.INSTANCE_FORCE_STOP,
    'reboot': AuditAction.INSTANCE_REBOOT,
}


class InstanceAddressesView(APIView):
    """实例网卡地址：从节点 Agent 读取 IPv4/IPv6。"""

    permission_classes = [CanViewInstance, RequiresPasswordChange]

    def get(self, request, pk: int) -> Response:
        """返回实例当前网卡地址。"""
        instance = instances_for(request.user).filter(pk=pk).first()
        if instance is None:
            raise AppError(ErrorCode.NOT_FOUND)
        payload = AgentClient(instance.node.endpoint).domain_addresses(instance.libvirt_domain_name)
        return Response(
            {
                'addresses': payload.get('addresses', []),
                'fetched_at': payload.get('fetched_at'),
            }
        )


class InstanceInterfacesView(APIView):
    """实例网卡接口：从节点 Agent 读取 vNIC 信息。"""

    permission_classes = [CanViewInstance, RequiresPasswordChange]

    def get(self, request, pk: int) -> Response:
        """返回实例当前网卡接口。"""
        instance = instances_for(request.user).filter(pk=pk).first()
        if instance is None:
            raise AppError(ErrorCode.NOT_FOUND)
        payload = AgentClient(instance.node.endpoint).domain_interfaces(
            instance.libvirt_domain_name
        )
        return Response({'interfaces': payload.get('interfaces', [])})


class InstanceConsoleView(APIView):
    """实例 VNC 控制台：签发短期 WebSocket 连接凭证。"""

    permission_classes = [CanViewInstance, RequiresPasswordChange]

    def get(self, request, pk: int) -> Response:
        """返回 noVNC 连接路径与 VNC 口令。"""
        instance = instances_for(request.user).filter(pk=pk).first()
        if instance is None:
            raise AppError(ErrorCode.NOT_FOUND)
        return Response(
            {
                'error': {
                    'code': 'CONFLICT',
                    'message': '控制台接口已升级，请刷新页面并使用会话授权接口',
                }
            },
            status=410,
        )


class InstanceActionView(APIView):
    """实例生命周期动作：start / shutdown / force-stop / reboot。"""

    permission_classes = [IsAuthenticated, RequiresPasswordChange]

    def post(self, request, pk: int, action: str) -> Response:
        """校验权限与状态后创建任务。"""
        codename = ACTION_PERMISSIONS.get(action)
        if codename is None:
            raise AppError(ErrorCode.NOT_FOUND, '不支持的操作')

        instance = instances_for(request.user).filter(pk=pk).first()
        if instance is None:
            raise AppError(ErrorCode.NOT_FOUND)

        check_permission(request.user, codename, target_type='instance', target_id=str(instance.pk))
        task = start_action(instance, request.user, action)

        if task is None:
            return Response(
                {'instance': InstanceSerializer(instance).data, 'task': None, 'idempotent': True},
                status=status.HTTP_200_OK,
            )

        record_audit(
            action=ACTION_AUDIT[action],
            actor=request.user,
            target_type='instance',
            target_id=str(instance.pk),
            task_id=str(task.pk),
            details={'name': instance.name, 'action': action},
        )
        return Response(
            {
                'instance': InstanceSerializer(instance).data,
                'task': {
                    'id': str(task.pk),
                    'status': task.status,
                    'status_url': f'/api/v1/tasks/{task.pk}',
                },
            },
            status=status.HTTP_202_ACCEPTED,
        )


class InstanceDeleteView(APIView):
    """删除实例：purge_disk 显式声明是否删除磁盘。"""

    permission_classes = [IsAuthenticated, RequiresPasswordChange]

    def delete(self, request, pk: int) -> Response:
        """创建删除任务并返回 202。"""
        instance = instances_for(request.user).filter(pk=pk).first()
        if instance is None:
            raise AppError(ErrorCode.NOT_FOUND)

        check_permission(
            request.user,
            'instances.delete_instance',
            target_type='instance',
            target_id=str(instance.pk),
        )
        purge_disk = str(request.query_params.get('purge_disk', 'false')).lower() in {
            '1',
            'true',
            'yes',
        }
        if purge_disk:
            check_permission(
                request.user,
                'instances.delete_disk_instance',
                target_type='instance',
                target_id=str(instance.pk),
            )

        task = request_delete(instance, request.user, purge_disk=purge_disk)
        record_audit(
            action=AuditAction.INSTANCE_DELETE,
            actor=request.user,
            target_type='instance',
            target_id=str(instance.pk),
            task_id=str(task.pk),
            details={'name': instance.name, 'purge_disk': purge_disk},
        )
        return Response(
            {
                'task': {
                    'id': str(task.pk),
                    'status': task.status,
                    'status_url': f'/api/v1/tasks/{task.pk}',
                }
            },
            status=status.HTTP_202_ACCEPTED,
        )


class DiskListView(generics.ListAPIView):
    """磁盘列表（只读，用于孤儿与容量核对）。"""

    permission_classes = [CanViewInstance, RequiresPasswordChange]
    serializer_class = DiskSerializer

    def get_queryset(self):
        """按实例或状态过滤。"""
        from apps.instances.disk_cleanup import disks_for

        queryset = disks_for(self.request.user)
        if self.request.query_params.get('retained') == 'true':
            queryset = queryset.filter(is_orphan=True).exclude(status='DELETED')
        instance_id = self.request.query_params.get('instance')
        if instance_id:
            queryset = queryset.filter(instance_id=instance_id)
        disk_status = self.request.query_params.get('status')
        if disk_status:
            queryset = queryset.filter(status=disk_status.upper())
        else:
            queryset = queryset.exclude(status='DELETED')
        return queryset.order_by('id')
