"""镜像路由。"""

from django.urls import path

from apps.images.uploads import (
    ImageVerifyView,
    UploadChunkView,
    UploadCompleteView,
    UploadCreateView,
    UploadDetailView,
)
from apps.images.views import ImageDetailView, ImageListCreateView

urlpatterns = [
    path('images/uploads', UploadCreateView.as_view()),
    path('images/uploads/<uuid:pk>', UploadDetailView.as_view()),
    path('images/uploads/<uuid:pk>/chunk', UploadChunkView.as_view()),
    path('images/uploads/<uuid:pk>/complete', UploadCompleteView.as_view()),
    path('images/<int:pk>/verify', ImageVerifyView.as_view()),
    path('images', ImageListCreateView.as_view(), name='image-list'),
    path('images/<int:pk>', ImageDetailView.as_view(), name='image-detail'),
]
