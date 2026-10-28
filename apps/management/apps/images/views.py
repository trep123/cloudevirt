"""镜像 API：列表、导入、详情、删除。"""

from django.db import transaction
from rest_framework import generics
from rest_framework.response import Response

from apps.audit.models import AuditAction
from apps.audit.services import record_audit
from apps.images.models import Image
from apps.images.serializers import ImageImportSerializer, ImageSerializer, ImageUpdateSerializer
from apps.images.services import delete_image
from apps.images.uploads import accepted, check_node, register_image
from common.permissions import CanDeleteImage, CanImportImage, CanViewImage, RequiresPasswordChange


class ImageListCreateView(generics.ListCreateAPIView):
    """镜像列表与导入。"""

    permission_classes = [RequiresPasswordChange]
    queryset = Image.objects.filter(is_deleted=False).select_related('node', 'upload')

    def get_permissions(self):
        """按动作选择权限类。"""
        if self.request.method == 'POST':
            return [CanImportImage(), RequiresPasswordChange()]
        return [CanViewImage(), RequiresPasswordChange()]

    def get_serializer_class(self):
        """写操作使用导入序列化器。"""
        if self.request.method == 'POST':
            return ImageImportSerializer
        return ImageSerializer

    def create(self, request, *args, **kwargs) -> Response:
        """登记节点文件并立即返回异步校验任务。"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        image, task = register_image(serializer.validated_data, request.user)
        record_audit(
            action=AuditAction.IMAGE_IMPORT,
            actor=request.user,
            target_type='image',
            target_id=str(image.pk),
            details={
                'name': image.name,
                'format': image.format,
                'status': image.status,
            },
        )
        return accepted(image, task)


class ImageDetailView(generics.RetrieveUpdateDestroyAPIView):
    """镜像详情、元数据更新与删除。"""

    permission_classes = [RequiresPasswordChange]
    queryset = Image.objects.filter(is_deleted=False)
    serializer_class = ImageSerializer

    def get_serializer_class(self):
        """更新只接受元数据字段。"""
        if self.request.method in {'PATCH', 'PUT'}:
            return ImageUpdateSerializer
        return ImageSerializer

    def get_permissions(self):
        """读、更新与删除使用不同权限。"""
        if self.request.method == 'GET':
            return [CanViewImage(), RequiresPasswordChange()]
        if self.request.method in {'PATCH', 'PUT'}:
            return [CanImportImage(), RequiresPasswordChange()]
        return [CanDeleteImage(), RequiresPasswordChange()]

    def perform_update(self, serializer) -> None:
        """更新镜像元数据并写审计。"""
        image = serializer.save()
        record_audit(
            action=AuditAction.IMAGE_UPDATE,
            actor=self.request.user,
            target_type='image',
            target_id=str(image.pk),
            details={
                'name': image.name,
                'os_family': image.os_family,
                'os_version': image.os_version,
            },
        )

    @transaction.atomic
    def perform_destroy(self, instance) -> None:
        """删除镜像：purge_file 参数显式声明是否删除节点文件。"""
        purge_raw = self.request.query_params.get('purge_file', 'true')
        purge_file = purge_raw.strip().lower() not in {'0', 'false', 'no'}
        instance = Image.objects.select_for_update().get(pk=instance.pk)
        if purge_file and instance.node:
            check_node(self.request.user, instance.node)
        delete_image(instance, purge_file=purge_file)
        record_audit(
            action=AuditAction.IMAGE_DELETE,
            actor=self.request.user,
            target_type='image',
            target_id=str(instance.pk),
            details={'name': instance.name, 'purge_file': purge_file},
        )
