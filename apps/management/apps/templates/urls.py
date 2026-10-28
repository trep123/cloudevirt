"""模板路由。"""

from django.urls import path

from apps.templates.versions import (
    DeploymentVersionListView,
    PublishTemplateVersionView,
    TemplateVersionView,
)
from apps.templates.views import TemplateDetailView, TemplateListCreateView

urlpatterns = [
    path('templates/deployments', DeploymentVersionListView.as_view()),
    path('templates/<int:pk>/versions', TemplateVersionView.as_view()),
    path('template-versions/<int:pk>/publish', PublishTemplateVersionView.as_view()),
    path('templates', TemplateListCreateView.as_view(), name='template-list'),
    path('templates/<int:pk>', TemplateDetailView.as_view(), name='template-detail'),
]
