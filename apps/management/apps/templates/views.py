"""模板 API。"""

from rest_framework import generics

from apps.accounts.administration import require_admin
from apps.audit.models import AuditAction
from apps.audit.services import record_audit
from apps.templates.models import Template
from apps.templates.serializers import TemplateSerializer
from common.permissions import CanManageTemplate, CanViewTemplate, RequiresPasswordChange


class AdminTemplatePermission(CanManageTemplate):
    def has_permission(self, request, view):
        require_admin(request.user, 'templates.add_template')
        return super().has_permission(request, view)


class TemplateListCreateView(generics.ListCreateAPIView):
    """模板列表与创建。"""

    permission_classes = [RequiresPasswordChange]
    queryset = Template.objects.filter(is_deleted=False)
    serializer_class = TemplateSerializer

    def get_queryset(self):
        from apps.templates.versions import visible_templates

        return visible_templates(self.request.user)

    def get_permissions(self):
        """按动作选择权限。"""
        if self.request.method == 'POST':
            return [AdminTemplatePermission(), RequiresPasswordChange()]
        return [CanViewTemplate(), RequiresPasswordChange()]

    def perform_create(self, serializer) -> None:
        """保存模板并写审计。"""
        require_admin(self.request.user, 'templates.add_template')
        template = serializer.save(created_by=self.request.user)
        record_audit(
            action=AuditAction.TEMPLATE_CREATE,
            actor=self.request.user,
            target_type='template',
            target_id=str(template.pk),
            details={
                'name': template.name,
                'vcpu': template.vcpu,
                'is_public': template.is_public,
                'assigned_users': list(template.assigned_users.values_list('pk', flat=True)),
            },
        )


class TemplateDetailView(generics.RetrieveUpdateDestroyAPIView):
    """模板详情、更新与删除。"""

    permission_classes = [AdminTemplatePermission, RequiresPasswordChange]
    queryset = Template.objects.filter(is_deleted=False)
    serializer_class = TemplateSerializer

    def get_queryset(self):
        from apps.templates.versions import visible_templates

        return visible_templates(self.request.user)

    def get_permissions(self):
        return (
            [CanViewTemplate(), RequiresPasswordChange()]
            if self.request.method == 'GET'
            else super().get_permissions()
        )

    def perform_update(self, serializer) -> None:
        """保存变更并写审计。"""
        require_admin(self.request.user, 'templates.add_template')
        previous = {
            'is_public': serializer.instance.is_public,
            'assigned_users': list(serializer.instance.assigned_users.values_list('pk', flat=True)),
        }
        template = serializer.save()
        record_audit(
            action=AuditAction.TEMPLATE_UPDATE,
            actor=self.request.user,
            target_type='template',
            target_id=str(template.pk),
            details={
                'name': template.name,
                'before': previous,
                'after': {
                    'is_public': template.is_public,
                    'assigned_users': list(template.assigned_users.values_list('pk', flat=True)),
                },
            },
        )

    def perform_destroy(self, instance) -> None:
        """软删除模板。"""
        require_admin(self.request.user, 'templates.add_template')
        instance.is_deleted = True
        instance.save(update_fields=['is_deleted', 'updated_at'])
        record_audit(
            action=AuditAction.TEMPLATE_DELETE,
            actor=self.request.user,
            target_type='template',
            target_id=str(instance.pk),
            details={'name': instance.name},
        )
