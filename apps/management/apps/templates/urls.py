"""模板路由。"""

from django.urls import path

from apps.templates.views import TemplateDetailView, TemplateListCreateView

urlpatterns = [
    path('templates', TemplateListCreateView.as_view(), name='template-list'),
    path('templates/<int:pk>', TemplateDetailView.as_view(), name='template-detail'),
]
