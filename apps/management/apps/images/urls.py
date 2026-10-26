"""镜像路由。"""

from django.urls import path

from apps.images.views import ImageDetailView, ImageListCreateView

urlpatterns = [
    path('images', ImageListCreateView.as_view(), name='image-list'),
    path('images/<int:pk>', ImageDetailView.as_view(), name='image-detail'),
]
