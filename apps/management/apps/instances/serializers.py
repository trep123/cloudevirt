"""实例序列化器。"""

from rest_framework import serializers

from apps.images.models import Image
from apps.instances.hardware import (
    HardwareSerializer,
    InitializationSerializer,
    validate_hardware_policy,
)
from apps.instances.models import Disk, Instance
from apps.nodes.models import Node


class DiskSerializer(serializers.ModelSerializer):
    """磁盘输出结构。"""

    instance_name = serializers.CharField(source='instance.name', read_only=True)

    class Meta:
        model = Disk
        fields = (
            'id',
            'instance',
            'instance_name',
            'role',
            'name',
            'relative_path',
            'format',
            'size_gib',
            'virtual_size_bytes',
            'target_dev',
            'status',
            'is_orphan',
        )


class InstanceSerializer(serializers.ModelSerializer):
    """实例输出结构，区分期望/观测/任务三种状态。"""

    node_name = serializers.CharField(source='node.name', read_only=True)
    image_name = serializers.CharField(source='image.name', read_only=True)
    disks = DiskSerializer(many=True, read_only=True)

    class Meta:
        model = Instance
        fields = (
            'id',
            'uuid',
            'name',
            'libvirt_domain_name',
            'node',
            'node_name',
            'image',
            'image_name',
            'network_name',
            'vcpu',
            'memory_mib',
            'disk_gib',
            'autostart',
            'creation_config',
            'initialization_status',
            'desired_state',
            'observed_state',
            'observed_state_updated_at',
            'observed_state_is_stale',
            'operation_status',
            'last_error_code',
            'last_error_message',
            'disks',
            'created_at',
            'updated_at',
        )
        read_only_fields = fields


class InstanceCreateSerializer(serializers.Serializer):
    """创建实例请求。"""

    name = serializers.CharField(max_length=64)
    node = serializers.PrimaryKeyRelatedField(queryset=Node.objects.filter(is_deleted=False))
    image = serializers.PrimaryKeyRelatedField(
        queryset=Image.objects.filter(is_deleted=False, status='READY')
    )
    vcpu = serializers.IntegerField(min_value=1)
    memory_mib = serializers.IntegerField(min_value=1)
    disk_gib = serializers.IntegerField(min_value=1)
    network_name = serializers.CharField(max_length=64, required=False, allow_blank=True)
    autostart = serializers.BooleanField(required=False, default=False)
    start_after_create = serializers.BooleanField(required=False, default=True)
    template = serializers.IntegerField(required=False, min_value=1)
    template_version = serializers.IntegerField(required=False, min_value=1)
    hardware = HardwareSerializer(required=False, default=dict)
    initialization = InitializationSerializer(required=False)
    data_disks = serializers.ListField(
        child=serializers.IntegerField(min_value=1, max_value=2048),
        max_length=8,
        required=False,
        default=list,
    )
    additional_networks = serializers.ListField(
        child=serializers.CharField(max_length=64, allow_blank=False),
        max_length=7,
        required=False,
        default=list,
    )

    def to_internal_value(self, data):
        from apps.templates.versions import resolve_version

        if data.get('template_version'):
            request = self.context.get('request')
            if request is None:
                raise serializers.ValidationError('模板创建需要授权上下文')
            try:
                version_id = int(data['template_version'])
            except ValueError, TypeError:
                raise serializers.ValidationError({'template_version': '版本 ID 无效'}) from None
            data = resolve_version({**data, 'template_version': version_id}, request.user)
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {key: ['未支持的创建字段'] for key in sorted(unknown)}
            )
        return super().to_internal_value(data)

    def validate(self, data):
        request = self.context.get('request')
        if request:
            validate_hardware_policy(data, request.user)
        from apps.networks.services import validate_network_for_instance

        names = data.get('additional_networks', [])
        if len(set(names)) != len(names) or data.get('network_name') in names:
            raise serializers.ValidationError({'additional_networks': '网卡网络重复'})
        for name in names:
            validate_network_for_instance(name)
        from apps.accounts.roles import is_admin
        from apps.templates.models import Template

        template_id = data.get('template')
        if template_id:
            request = self.context.get('request')
            template = Template.objects.filter(pk=template_id, is_deleted=False).first()
            if template is None or (
                not template.is_public
                and not (
                    request
                    and (is_admin(request.user) or template.created_by_id == request.user.pk)
                )
            ):
                raise serializers.ValidationError({'template': '模板不存在或无权访问'})
        image = data['image']
        if image.node_id and image.node_id != data['node'].pk:
            raise serializers.ValidationError({'image': '镜像不在所选节点，请选择已同步镜像'})
        if (
            image.format != 'ISO'
            and image.virtual_size_bytes
            and data['disk_gib'] * 1024**3 < image.virtual_size_bytes
        ):
            raise serializers.ValidationError({'disk_gib': '系统盘小于镜像虚拟容量'})
        return data


class TaskReferenceSerializer(serializers.Serializer):
    """创建后返回的任务引用。"""

    id = serializers.UUIDField()
    status = serializers.CharField()
    status_url = serializers.CharField()
