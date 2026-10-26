"""CloudVirt 管理后端 URL 总入口。"""

from django.urls import path

from common.views import health

urlpatterns = [
    path('api/v1/health', health, name='health'),
]
