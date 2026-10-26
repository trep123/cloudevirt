"""任务路由。"""

from django.urls import path

from apps.tasks.views import (
    TaskCancelView,
    TaskDetailView,
    TaskListView,
    TaskRetryView,
)

urlpatterns = [
    path('tasks', TaskListView.as_view(), name='task-list'),
    path('tasks/<uuid:pk>', TaskDetailView.as_view(), name='task-detail'),
    path('tasks/<uuid:pk>/cancel', TaskCancelView.as_view(), name='task-cancel'),
    path('tasks/<uuid:pk>/retry', TaskRetryView.as_view(), name='task-retry'),
]
