from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.administration import require_admin
from apps.accounts.roles import is_admin
from apps.audit.services import record_audit
from apps.templates.models import Template, TemplateVersion
from common.permissions import CanViewTemplate, RequiresPasswordChange

CONFIG_FIELDS = {
    'data_disks',
    'additional_networks',
    'hardware',
    'image',
    'vcpu',
    'memory_mib',
    'disk_gib',
    'network_name',
    'autostart',
    'start_after_create',
}


def visible_templates(user):
    query = Template.objects.filter(is_deleted=False)
    return query if is_admin(user) else query.filter(Q(is_public=True) | Q(created_by=user))


class VersionSerializer(serializers.ModelSerializer):
    template_name = serializers.CharField(source='template.name', read_only=True)

    class Meta:
        model = TemplateVersion
        fields = [
            'id',
            'template',
            'template_name',
            'version',
            'configuration',
            'constraints',
            'published',
            'created_at',
        ]
        read_only_fields = ['id', 'template', 'version', 'published', 'created_at']

    def validate(self, data):
        config = data.get('configuration', {})
        if not isinstance(config, dict):
            raise serializers.ValidationError({'configuration': '必须是配置对象'})
        from apps.instances.hardware import HardwareSerializer

        if 'hardware' in config:
            hardware = HardwareSerializer(data=config['hardware'])
            hardware.is_valid(raise_exception=True)
            config['hardware'] = hardware.validated_data
        for key, field in [
            (
                'data_disks',
                serializers.ListField(
                    child=serializers.IntegerField(min_value=1, max_value=2048), max_length=8
                ),
            ),
            (
                'additional_networks',
                serializers.ListField(
                    child=serializers.CharField(max_length=64, allow_blank=False), max_length=7
                ),
            ),
        ]:
            if key in config:
                config[key] = field.run_validation(config[key])
        constraints = data.get('constraints', {})
        if not isinstance(config, dict) or set(config) - CONFIG_FIELDS:
            raise serializers.ValidationError({'configuration': '存在不支持的配置字段'})
        if not isinstance(constraints, dict) or set(constraints) - {'locked', 'bounds'}:
            raise serializers.ValidationError({'constraints': '约束仅支持 locked、bounds'})
        locked = constraints.get('locked', [])
        if not isinstance(locked, list) or any(
            not isinstance(key, str) or key not in config for key in locked
        ):
            raise serializers.ValidationError({'constraints': '锁定项必须是已提供默认值的字段'})
        bounds = constraints.get('bounds', {})
        if not isinstance(bounds, dict) or set(bounds) - {'vcpu', 'memory_mib', 'disk_gib'}:
            raise serializers.ValidationError({'constraints': '数值约束字段无效'})
        for key, limits in bounds.items():
            if (
                not isinstance(limits, dict)
                or set(limits) != {'min', 'max'}
                or any(type(limits[v]) is not int for v in ['min', 'max'])
                or not 0 < limits['min'] <= limits['max']
            ):
                raise serializers.ValidationError({'constraints': f'{key} 上下限无效'})
        for key in ['image', 'vcpu', 'memory_mib', 'disk_gib']:
            if key in config and (type(config[key]) is not int or config[key] <= 0):
                raise serializers.ValidationError({'configuration': f'{key} 必须为正整数'})
        for key in ['autostart', 'start_after_create']:
            if key in config and type(config[key]) is not bool:
                raise serializers.ValidationError({'configuration': f'{key} 必须为布尔值'})
        if 'network_name' in config and (
            not isinstance(config['network_name'], str) or len(config['network_name']) > 64
        ):
            raise serializers.ValidationError({'configuration': 'network_name 无效'})
        return data


class DeploymentVersionListView(APIView):
    permission_classes = [CanViewTemplate, RequiresPasswordChange]

    def get(self, request):
        versions = (
            TemplateVersion.objects.filter(
                template__in=visible_templates(request.user), published=True
            )
            .select_related('template')
            .order_by('template__name', '-version')
        )
        return Response({'results': VersionSerializer(versions, many=True).data})


class TemplateVersionView(APIView):
    permission_classes = [RequiresPasswordChange]

    @transaction.atomic
    def post(self, request, pk):
        require_admin(request.user, 'templates.add_template')
        parent = get_object_or_404(Template.objects.select_for_update(), pk=pk, is_deleted=False)
        if set(request.data) - {'configuration', 'constraints'}:
            raise serializers.ValidationError('存在未知模板字段')
        serializer = VersionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        latest = parent.versions.order_by('-version').first()
        version = serializer.save(
            template=parent,
            version=(latest.version + 1 if latest else 1),
            configuration={
                'vcpu': parent.vcpu,
                'memory_mib': parent.memory_mib,
                'disk_gib': parent.disk_gib,
                **serializer.validated_data.get('configuration', {}),
            },
        )
        record_audit(
            action='TEMPLATE_VERSION_DRAFT',
            actor=request.user,
            target_type='template',
            target_id=str(pk),
            details={'version': version.version},
        )
        return Response(VersionSerializer(version).data, status=201)


class PublishTemplateVersionView(APIView):
    permission_classes = [RequiresPasswordChange]

    @transaction.atomic
    def post(self, request, pk):
        require_admin(request.user, 'templates.add_template')
        version = get_object_or_404(
            TemplateVersion.objects.select_for_update().select_related('template'),
            pk=pk,
            template__is_deleted=False,
        )
        config = {
            'vcpu': version.template.vcpu,
            'memory_mib': version.template.memory_mib,
            'disk_gib': version.template.disk_gib,
            **version.configuration,
        }
        from apps.images.models import Image
        from apps.instances.services import validate_spec
        from apps.networks.services import validate_network_for_instance

        validate_spec(
            name='template-validation',
            vcpu=config['vcpu'],
            memory_mib=config['memory_mib'],
            disk_gib=config['disk_gib'],
        )
        image = Image.objects.filter(
            pk=config.get('image'), is_deleted=False, status='READY'
        ).first()
        if image is None:
            raise serializers.ValidationError({'image': '发布前需指定可用镜像'})
        if len(image.checksum_sha256) != 64:
            raise serializers.ValidationError({'image': '镜像需重新登记以获取摘要'})
        for field, bounds in version.constraints.get('bounds', {}).items():
            if not bounds['min'] <= config[field] <= bounds['max']:
                raise serializers.ValidationError({field: '默认值超出模板允许范围'})
        if (
            image.format != 'ISO'
            and image.virtual_size_bytes
            and image.virtual_size_bytes > config['disk_gib'] * 1024**3
        ):
            raise serializers.ValidationError({'disk_gib': '小于镜像虚拟容量'})
        validate_network_for_instance(config.get('network_name', ''))
        if version.published:
            return Response(VersionSerializer(version).data)
        version.image_checksum = image.checksum_sha256
        version.published = True
        version.save(update_fields=['published', 'image_checksum'])
        record_audit(
            action='TEMPLATE_PUBLISH',
            actor=request.user,
            target_type='template',
            target_id=str(version.template_id),
            details={'version': version.version},
        )
        return Response(VersionSerializer(version).data)


def resolve_version(data, user):
    version_id = data.get('template_version')
    if not version_id:
        return data
    version = get_object_or_404(
        TemplateVersion.objects.select_related('template'),
        pk=version_id,
        published=True,
        template__in=visible_templates(user),
    )
    from apps.images.models import Image

    if not Image.objects.filter(
        pk=version.configuration.get('image'),
        checksum_sha256=version.image_checksum,
        status='READY',
        is_deleted=False,
    ).exists():
        raise serializers.ValidationError(
            {'template_version': '模板镜像已变更或不可用，请重新发布版本'}
        )
    config = {
        'vcpu': version.template.vcpu,
        'memory_mib': version.template.memory_mib,
        'disk_gib': version.template.disk_gib,
        **version.configuration,
        **data,
    }
    for field in version.constraints.get('locked', []):
        if config.get(field) != version.configuration.get(field):
            raise serializers.ValidationError({field: '此字段已被模板锁定'})
    for field, bounds in version.constraints.get('bounds', {}).items():
        value = config.get(field)
        if type(value) is not int or not bounds['min'] <= value <= bounds['max']:
            raise serializers.ValidationError({field: '超出模板允许范围'})
    config['template'] = version.template_id
    return config
