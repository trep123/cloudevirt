"""实例序列化器。"""

from rest_framework import serializers

from apps.images.models import Image
from apps.instances.models import Disk, Instance
from apps.nodes.models import Node


class DiskSerializer(serializers.ModelSerializer):
    """磁盘输出结构。"""

    class Meta:
        model = Disk
        fields = (
            'id',
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


class TaskReferenceSerializer(serializers.Serializer):
    """创建后返回的任务引用。"""

    id = serializers.UUIDField()
    status = serializers.CharField()
    status_url = serializers.CharField()
