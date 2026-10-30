"""实例序列化器。"""

from rest_framework import serializers

from apps.images.models import Image
from apps.instances.hardware import (
    HardwareSerializer,
    InitializationSerializer,
    StaticNetworkSerializer,
    validate_hardware_policy,
)
from apps.instances.models import Disk, Instance
from apps.nodes.models import Node


class DiskSerializer(serializers.ModelSerializer):
    """磁盘输出结构。"""

    instance_name = serializers.CharField(source='instance.name', read_only=True)
    instance_deleted = serializers.BooleanField(source='instance.is_deleted', read_only=True)
    node_name = serializers.CharField(source='instance.node.name', read_only=True)
    can_delete = serializers.SerializerMethodField()

    def get_can_delete(self, obj):
        from apps.instances.disk_cleanup import eligible

        request = self.context.get('request')
        return bool(
            request and eligible(obj) and request.user.has_perm('instances.delete_disk_instance')
        )

    class Meta:
        model = Disk
        fields = (
            'id',
            'instance',
            'instance_name',
            'instance_deleted',
            'node_name',
            'can_delete',
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
    existing_system_disk = serializers.IntegerField(required=False, min_value=1)
    template_version = serializers.IntegerField(required=False, min_value=1)
    hardware = HardwareSerializer(required=False, default=dict)
    initialization = InitializationSerializer(required=False)
    static_networks = serializers.DictField(
        child=StaticNetworkSerializer(), required=False, default=dict
    )
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

        if data.get('existing_system_disk'):
            from apps.instances.disk_sources import source_disk

            request = self.context.get('request')
            if request is None:
                raise serializers.ValidationError(
                    {'existing_system_disk': '已有系统盘需要管理员授权'}
                )
            disk_id = self.fields['existing_system_disk'].run_validation(
                data['existing_system_disk']
            )
            disk = source_disk(request.user, disk_id)
            if data.get('template_version') or data.get('initialization'):
                raise serializers.ValidationError(
                    {'existing_system_disk': '已有系统盘不能与部署模板或初始化混用'}
                )
            data = {**data, 'image': disk.instance.image_id}
            self.fields['image'].queryset = Image.objects.filter(pk=disk.instance.image_id)
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
        static = data.get('static_networks', {})
        if len(static) > 8 or set(static) - set([data.get('network_name', '')] + names):
            raise serializers.ValidationError(
                {'static_networks': '静态配置只能引用已选择的网卡网络'}
            )
        if static and not data.get('initialization'):
            raise serializers.ValidationError({'static_networks': '静态网络需要启用 cloud-init'})
        if sum(bool(value.get('default_route')) for value in static.values()) > 1:
            raise serializers.ValidationError({'static_networks': '只能配置一条默认路由'})
        if len(set(names)) != len(names) or data.get('network_name') in names:
            raise serializers.ValidationError({'additional_networks': '网卡网络重复'})
        for name in names:
            validate_network_for_instance(name, data['node'])
        from apps.templates.versions import visible_templates

        template_id = data.get('template')
        if template_id:
            request = self.context.get('request')
            if (
                request is None
                or not visible_templates(request.user).filter(pk=template_id).exists()
            ):
                raise serializers.ValidationError({'template': '模板不存在或无权访问'})
        image = data['image']
        if data.get('existing_system_disk'):
            from apps.instances.disk_sources import source_disk

            disk = source_disk(request.user, data['existing_system_disk'], data['node'].pk)
            if data['disk_gib'] < disk.size_gib:
                raise serializers.ValidationError({'disk_gib': '新系统盘不能小于源系统盘'})
            return data
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
