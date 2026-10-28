from django.urls import path

from .views import DesktopAuthorizeView, DesktopCreateView, DesktopLeaseView

urlpatterns = [
    path('console/instances/<int:pk>/sessions', DesktopCreateView.as_view()),
    path('console/authorize', DesktopAuthorizeView.as_view()),
    path('console/sessions/<uuid:pk>', DesktopLeaseView.as_view()),
]
