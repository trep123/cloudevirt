from django.urls import path

from .broadcast_views import (
    BroadcastControlView,
    BroadcastsView,
    PublicBroadcastView,
    PublicWatchLeaseView,
)
from .media import MediaCreateView, MediaLeaseView, MediaSourceDetailView, MediaSourcesView
from .views import DesktopAuthorizeView, DesktopCreateView, DesktopLeaseView

urlpatterns = [
    path('console/instances/<int:pk>/broadcasts', BroadcastsView.as_view()),
    path('console/broadcasts/<uuid:pk>', BroadcastControlView.as_view()),
    path('console/broadcasts/<uuid:pk>/watch', PublicBroadcastView.as_view()),
    path('console/watch-sessions/<uuid:pk>', PublicWatchLeaseView.as_view()),
    path('console/instances/<int:pk>/media-sources', MediaSourcesView.as_view()),
    path('console/media-sources/<int:pk>', MediaSourceDetailView.as_view()),
    path('console/media-sources/<int:pk>/sessions', MediaCreateView.as_view()),
    path('console/media-sessions/<uuid:pk>', MediaLeaseView.as_view()),
    path('console/instances/<int:pk>/sessions', DesktopCreateView.as_view()),
    path('console/authorize', DesktopAuthorizeView.as_view()),
    path('console/sessions/<uuid:pk>', DesktopLeaseView.as_view()),
]
