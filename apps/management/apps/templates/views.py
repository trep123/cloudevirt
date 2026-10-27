"""模板 API。"""

from rest_framework import generics

from apps.audit.models import AuditAction
from apps.audit.services import record_audit
from apps.templates.models import Template
from apps.templates.serializers import TemplateSerializer
from common.permissions import CanManageTemplate, CanViewTemplate, RequiresPasswordChange


class TemplateListCreateView(generics.ListCreateAPIView):
    """模板列表与创建。"""

    permission_classes = [RequiresPasswordChange]
    queryset = Template.objects.filter(is_deleted=False)
    serializer_class = TemplateSerializer

    def get_permissions(self):
        """按动作选择权限。"""
        if self.request.method == 'POST':
            return [CanManageTemplate(), RequiresPasswordChange()]
        return [CanViewTemplate(), RequiresPasswordChange()]

    def perform_create(self, serializer) -> None:
        """保存模板并写审计。"""
        template = serializer.save(created_by=self.request.user)
        record_audit(
            action=AuditAction.TEMPLATE_CREATE,
            actor=self.request.user,
            target_type='template',
            target_id=str(template.pk),
            details={'name': template.name, 'vcpu': template.vcpu},
        )


class TemplateDetailView(generics.RetrieveUpdateDestroyAPIView):
    """模板详情、更新与删除。"""

    permission_classes = [CanManageTemplate, RequiresPasswordChange]
    queryset = Template.objects.filter(is_deleted=False)
    serializer_class = TemplateSerializer

    def perform_update(self, serializer) -> None:
        """保存变更并写审计。"""
        template = serializer.save()
        record_audit(
            action=AuditAction.TEMPLATE_UPDATE,
            actor=self.request.user,
            target_type='template',
            target_id=str(template.pk),
            details={'name': template.name},
        )

    def perform_destroy(self, instance) -> None:
        """软删除模板。"""
        instance.is_deleted = True
        instance.save(update_fields=['is_deleted', 'updated_at'])
        record_audit(
            action=AuditAction.TEMPLATE_DELETE,
            actor=self.request.user,
            target_type='template',
            target_id=str(instance.pk),
            details={'name': instance.name},
        )
