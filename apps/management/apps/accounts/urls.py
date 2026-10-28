"""账户与用户管理路由。"""

from django.urls import path

from apps.accounts.views import (
    ChangePasswordView,
    LoginView,
    LogoutView,
    MeView,
    UserAuditView,
    UserDetailView,
    UserListCreateView,
    UserResetPasswordView,
)

from .bulk import (
    AccountBatchDetailView,
    AccountBatchDownloadView,
    AccountBatchView,
    AccountTemplateView,
)

urlpatterns = [
    path('users/batches', AccountBatchView.as_view()),
    path('users/batches/<uuid:pk>', AccountBatchDetailView.as_view()),
    path('users/batches/<uuid:pk>/download', AccountBatchDownloadView.as_view()),
    path('users/import-template', AccountTemplateView.as_view()),
    path('auth/login', LoginView.as_view(), name='auth-login'),
    path('auth/logout', LogoutView.as_view(), name='auth-logout'),
    path('auth/me', MeView.as_view(), name='auth-me'),
    path('auth/change-password', ChangePasswordView.as_view(), name='auth-change-password'),
    path('users', UserListCreateView.as_view(), name='user-list'),
    path('users/<int:pk>', UserDetailView.as_view(), name='user-detail'),
    path('users/<int:pk>/audit', UserAuditView.as_view(), name='user-audit'),
    path(
        'users/<int:pk>/reset-password', UserResetPasswordView.as_view(), name='user-reset-password'
    ),
]
