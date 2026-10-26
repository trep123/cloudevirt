"""镜像 API：列表、导入、详情、删除。"""

from rest_framework import generics
from rest_framework.response import Response

from apps.audit.models import AuditAction
from apps.audit.services import record_audit
from apps.images.models import Image
from apps.images.serializers import ImageImportSerializer, ImageSerializer
from apps.images.services import delete_image, import_image
from common.permissions import CanDeleteImage, CanImportImage, CanViewImage, RequiresPasswordChange


class ImageListCreateView(generics.ListCreateAPIView):
    """镜像列表与导入。"""

    permission_classes = [RequiresPasswordChange]
    queryset = Image.objects.filter(is_deleted=False)

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
        """导入镜像并以输出序列化器回显真实检测结果。"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        image = import_image(
            name=serializer.validated_data['name'],
            node=serializer.validated_data['node'],
            relative_path=serializer.validated_data['relative_path'],
            created_by=request.user,
            os_family=serializer.validated_data.get('os_family', ''),
            os_version=serializer.validated_data.get('os_version', ''),
        )
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
        return Response(
            ImageSerializer(image).data,
            status=201 if image.is_ready else 200,
        )


class ImageDetailView(generics.RetrieveDestroyAPIView):
    """镜像详情与删除。"""

    permission_classes = [RequiresPasswordChange]
    queryset = Image.objects.filter(is_deleted=False)
    serializer_class = ImageSerializer

    def get_permissions(self):
        """读操作与删除操作权限不同。"""
        if self.request.method == 'GET':
            return [CanViewImage(), RequiresPasswordChange()]
        return [CanDeleteImage(), RequiresPasswordChange()]

    def perform_destroy(self, instance) -> None:
        """删除镜像：purge_file 参数显式声明是否删除节点文件。"""
        purge_raw = self.request.query_params.get('purge_file', 'true')
        purge_file = purge_raw.strip().lower() not in {'0', 'false', 'no'}
        delete_image(instance, purge_file=purge_file)
        record_audit(
            action=AuditAction.IMAGE_DELETE,
            actor=self.request.user,
            target_type='image',
            target_id=str(instance.pk),
            details={'name': instance.name, 'purge_file': purge_file},
        )
