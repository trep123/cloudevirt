"""CloudVirt 管理后端 URL 总入口。"""

from django.urls import include, path

from common.views import health

urlpatterns = [
    path('api/v1/health', health, name='health'),
    path('api/v1/', include('apps.accounts.urls')),
    path('api/v1/', include('apps.nodes.urls')),
    path('api/v1/', include('apps.tasks.urls')),
    path('api/v1/', include('apps.images.urls')),
    path('api/v1/', include('apps.instances.urls')),
    path('api/v1/', include('apps.networks.urls')),
    path('api/v1/', include('apps.monitoring.urls')),
]

# API 前缀下不返回 HTML 错误页，统一使用 JSON 错误结构
handler404 = 'common.views.json_404'
handler500 = 'common.views.json_500'
