"""网络序列化器。"""

from rest_framework import serializers

from apps.networks.models import Network


class NetworkSerializer(serializers.ModelSerializer):
    """网络输出结构。"""

    is_usable = serializers.BooleanField(read_only=True)

    class Meta:
        model = Network
        fields = (
            'id',
            'name',
            'type',
            'bridge',
            'vlan_id',
            'is_default',
            'is_management',
            'description',
            'is_usable',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('created_at', 'updated_at')

    def validate_name(self, value: str) -> str:
        """校验名称格式。"""
        if len(value) < 2 or len(value) > 64:
            raise serializers.ValidationError('名称长度必须在 2-64 之间')
        if not value.replace('-', '').replace('_', '').isalnum():
            raise serializers.ValidationError('名称只能包含字母、数字、连字符与下划线')
        return value

    def validate(self, attrs: dict) -> dict:
        """禁止把网络同时标记为默认与管理网。"""
        if attrs.get('is_management') and attrs.get('is_default'):
            raise serializers.ValidationError('管理网不能作为默认网络')
        return attrs
