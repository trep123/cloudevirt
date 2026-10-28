from django.urls import path

from .broadcast_views import (
    BroadcastControlView,
    BroadcastsView,
    PublicBroadcastView,
    PublicWatchLeaseView,
)
from .media import MediaCreateView, MediaLeaseView, MediaSourceDetailView, MediaSourcesView
from .tab_shares import TabShareLeaseView, TabSharesView
from .views import DesktopAuthorizeView, DesktopCreateView, DesktopLeaseView
from .workspaces import (
    MyWorkspaceView,
    WorkspaceBootstrapView,
    WorkspaceControlLeaseView,
    WorkspaceControlView,
    WorkspaceLinkView,
)

urlpatterns = [
    path('console/tab-shares', TabSharesView.as_view()),
    path('console/tab-shares/requests/<uuid:request_id>', TabShareLeaseView.as_view()),
    path('console/workspaces/my', MyWorkspaceView.as_view()),
    path('console/workspaces/my/link', WorkspaceLinkView.as_view()),
    path('console/workspaces/<uuid:pk>/bootstrap', WorkspaceBootstrapView.as_view()),
    path('console/workspaces/<uuid:pk>/sessions', WorkspaceControlView.as_view()),
    path('console/workspace-sessions/<uuid:pk>', WorkspaceControlLeaseView.as_view()),
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
