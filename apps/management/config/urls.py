"""CloudVirt 管理后端 URL 总入口。"""

from django.urls import include, path

from common.console import AuditListView, DashboardView, QuotaView, RoleListView
from common.views import health

urlpatterns = [
    path('api/v1/', include('apps.console.urls')),
    path('api/v1/', include('apps.infrastructure.urls')),
    path('api/v1/', include('common.console_urls')),
    path('api/v1/console/dashboard', DashboardView.as_view(), name='console-dashboard'),
    path('api/v1/console/audit', AuditListView.as_view(), name='console-audit'),
    path('api/v1/console/roles', RoleListView.as_view(), name='console-roles'),
    path('api/v1/console/quota', QuotaView.as_view(), name='console-quota'),
    path('api/v1/health', health, name='health'),
    path('api/v1/', include('apps.accounts.urls')),
    path('api/v1/', include('apps.nodes.urls')),
    path('api/v1/', include('apps.tasks.urls')),
    path('api/v1/', include('apps.images.urls')),
    path('api/v1/', include('apps.instances.urls')),
    path('api/v1/', include('apps.networks.urls')),
    path('api/v1/', include('apps.templates.urls')),
    path('api/v1/', include('apps.monitoring.urls')),
]

# API 前缀下不返回 HTML 错误页，统一使用 JSON 错误结构
handler404 = 'common.views.json_404'
handler500 = 'common.views.json_500'
