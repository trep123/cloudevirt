"""镜像序列化器。"""

from rest_framework import serializers

from apps.images.models import Image, ImageFormat
from apps.nodes.models import Node


class ImageSerializer(serializers.ModelSerializer):
    """镜像输出结构。"""

    is_ready = serializers.BooleanField(read_only=True)
    node_name = serializers.CharField(source='node.name', read_only=True, default='')
    upload_id = serializers.UUIDField(source='upload.pk', read_only=True, default=None)
    storage_pool_name = serializers.CharField(
        source='storage_pool.name', read_only=True, allow_null=True
    )

    class Meta:
        model = Image
        fields = (
            'id',
            'name',
            'node',
            'node_name',
            'upload_id',
            'format',
            'relative_path',
            'storage_pool',
            'storage_pool_name',
            'size_bytes',
            'virtual_size_bytes',
            'checksum_sha256',
            'status',
            'os_family',
            'os_version',
            'supports_cloud_init',
            'error_code',
            'error_message',
            'is_ready',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'format',
            'size_bytes',
            'virtual_size_bytes',
            'checksum_sha256',
            'status',
            'error_code',
            'error_message',
            'created_at',
            'updated_at',
        )


class ImageUpdateSerializer(serializers.ModelSerializer):
    """只允许维护镜像元数据，禁止直接改文件路径与检测结果。"""

    class Meta:
        model = Image
        fields = ('os_family', 'os_version', 'supports_cloud_init')

    def validate_supports_cloud_init(self, value):
        from apps.accounts.roles import is_admin

        request = self.context.get('request')
        if not request or not is_admin(request.user):
            raise serializers.ValidationError('仅平台管理员可确认镜像初始化能力')
        return value


class ImageImportSerializer(serializers.ModelSerializer):
    """导入镜像请求。"""

    node = serializers.PrimaryKeyRelatedField(
        queryset=Node.objects.filter(is_deleted=False), help_text='执行检查的节点'
    )
    relative_path = serializers.CharField(max_length=255)
    storage_pool = serializers.CharField(
        max_length=64, required=False, default='', allow_blank=True
    )

    class Meta:
        model = Image
        fields = (
            'id',
            'name',
            'node',
            'relative_path',
            'storage_pool',
            'os_family',
            'os_version',
            'format',
            'status',
        )
        read_only_fields = ('id', 'format', 'status')
        extra_kwargs = {
            'os_family': {'required': False},
            'os_version': {'required': False},
        }

    def validate_name(self, value: str) -> str:
        """校验名称长度与重复。"""
        if len(value) < 2:
            raise serializers.ValidationError('镜像名称至少 2 个字符')
        if Image.objects.filter(name=value, is_deleted=False).exists():
            raise serializers.ValidationError('镜像名称已存在')
        return value

    def validate_format(self, value: str) -> str:
        """格式由 Agent 检测结果决定，不接受客户端指定。"""
        if value and value not in ImageFormat.values:
            raise serializers.ValidationError('不支持的镜像格式')
        return value
