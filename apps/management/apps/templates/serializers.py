"""模板序列化器。"""

from rest_framework import serializers

from apps.templates.models import Template


class TemplateSerializer(serializers.ModelSerializer):
    """模板输出结构。"""

    class Meta:
        model = Template
        fields = (
            'id',
            'name',
            'description',
            'vcpu',
            'memory_mib',
            'disk_gib',
            'is_public',
            'created_by',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('created_by', 'created_at', 'updated_at')

    def validate_name(self, value: str) -> str:
        """校验名称唯一性与格式。"""
        value = (value or '').strip()
        if len(value) < 2:
            raise serializers.ValidationError('名称至少 2 个字符')
        qs = Template.objects.filter(name=value, is_deleted=False)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('模板名称已存在')
        return value

    def validate_vcpu(self, value: int) -> int:
        """校验 vCPU 范围。"""
        if not isinstance(value, int) or value <= 0 or value > 64:
            raise serializers.ValidationError('vCPU 必须为 1-64')
        return value

    def validate_memory_mib(self, value: int) -> int:
        """校验内存范围。"""
        if not isinstance(value, int) or value < 128 or value > 131072:
            raise serializers.ValidationError('内存必须在 128-131072 MiB')
        return value

    def validate_disk_gib(self, value: int) -> int:
        """校验磁盘范围。"""
        if not isinstance(value, int) or value <= 0 or value > 2048:
            raise serializers.ValidationError('磁盘必须为 1-2048 GiB')
        return value
