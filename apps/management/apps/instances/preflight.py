from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.administration import limit_nodes
from apps.infrastructure.placement import pool_available_bytes, select_storage_pool
from apps.instances.hardware import validate_creation_capabilities
from apps.instances.serializers import InstanceCreateSerializer
from apps.instances.services import available_resources, validate_spec
from apps.networks.services import validate_network_for_instance
from apps.nodes.access import user_can_access
from apps.nodes.client import AgentClient
from apps.nodes.models import NodePermission
from common.errors import AppError, ErrorCode
from common.permissions import CanCreateInstance, RequiresPasswordChange
from common.quota import enforce_quota, quota_for


class CreatePreflightView(APIView):
    permission_classes = [CanCreateInstance, RequiresPasswordChange]

    def post(self, request):
        serializer = InstanceCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        node = data['node']
        image = data['image']
        validate_spec(**{key: data[key] for key in ['name', 'vcpu', 'memory_mib', 'disk_gib']})
        if node.pk not in limit_nodes(
            request.user, {node.pk}, 'instances.add_instance'
        ) or not user_can_access(request.user, node, NodePermission.OPERATE):
            raise AppError(ErrorCode.PERMISSION_DENIED, '无权在此节点创建实例')
        if not node.is_schedulable:
            raise AppError(ErrorCode.NODE_OFFLINE, '目标节点不可调度')
        validate_network_for_instance(data.get('network_name', ''), node)
        total_disk = data['disk_gib'] + sum(data.get('data_disks', []))
        enforce_quota(
            request.user, vcpu=data['vcpu'], memory_mib=data['memory_mib'], disk_gib=total_disk
        )
        if image and not data.get('existing_system_disk') and len(image.checksum_sha256) != 64:
            raise AppError(ErrorCode.CONFLICT, '镜像摘要缺失，请重新登记校验')
        resources = available_resources(node)
        selected_pool = select_storage_pool(request.user, node, data.get('storage_pool', ''))
        if selected_pool:
            if data.get('existing_system_file'):
                raise AppError(ErrorCode.INVALID_ARGUMENT, '直接使用已有系统盘仅支持默认磁盘目录')
            resources['disk_bytes'] = pool_available_bytes(node, selected_pool)
        requested = {
            'vcpu': data['vcpu'],
            'memory_mib': data['memory_mib'],
            'disk_bytes': (
                sum(data.get('data_disks', []))
                if data.get('existing_system_file') and data.get('clone_mode', 'direct') == 'direct'
                else total_disk
            )
            * 1024**3,
        }
        if any(requested[key] > resources[key] for key in requested):
            raise AppError(
                ErrorCode.INSUFFICIENT_RESOURCE,
                '目标节点容量不足',
                details={'available': resources, 'requested': requested},
            )
        capabilities = AgentClient(node.endpoint).get_json('/api/v1/node/capabilities')
        if data.get('existing_system_disk') and capabilities.get('retained_disk_clone') is not True:
            raise AppError(ErrorCode.CONFLICT, '节点需升级以支持已有系统盘克隆')
        if (
            data.get('existing_system_file')
            and capabilities.get('existing_disk_attach') is not True
        ):
            raise AppError(ErrorCode.CONFLICT, '节点需升级以支持直接使用磁盘')
        if data.get('clone_mode') == 'linked' and capabilities.get('linked_clone') is not True:
            raise AppError(ErrorCode.CONFLICT, '节点尚不支持链接克隆')
        validate_creation_capabilities(data, capabilities)
        if not all(
            capabilities.get(key) is True for key in ['image_clone', 'iso_install', 'start_control']
        ):
            raise AppError(ErrorCode.CONFLICT, '节点 Agent 尚未支持可靠镜像创建，请先升级')
        normalized = {
            key: (value.pk if key in ['node', 'image'] and value is not None else value)
            for key, value in data.items()
        }
        response = Response(
            {
                'valid': True,
                'configuration': normalized,
                'quota': quota_for(request.user),
                'requested': requested,
                'capabilities': capabilities,
                'valid_for_seconds': 60,
                'warnings': ['预校验不预留容量，正式提交会再次检查'],
                'deployment_mode': 'existing_disk'
                if data.get('existing_system_file') and data.get('clone_mode', 'direct') == 'direct'
                else ('iso' if image and image.format == 'ISO' else 'image'),
            }
        )
        response['Cache-Control'] = 'no-store'
        return response
