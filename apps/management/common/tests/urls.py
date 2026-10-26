"""测试专用路由：仅用于验证统一错误结构、分页与 request_id 契约。"""

from django.http import Http404
from django.urls import path
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.errors import AppError, ErrorCode
from common.pagination import StandardPagination

TOTAL_ITEMS = 250


class AppErrorView(APIView):
    """抛出业务异常，用于验证错误码映射。"""

    permission_classes = []

    def get(self, request):
        """抛出 INSUFFICIENT_RESOURCE 业务异常。"""
        raise AppError(ErrorCode.INSUFFICIENT_RESOURCE, details={'resource': 'memory_mib'})


class ValidationErrorView(APIView):
    """抛出序列化器校验错误。"""

    permission_classes = []

    def get(self, request):
        """抛出字段级校验错误。"""
        raise ValidationError({'memory_mib': ['必须大于 0']})


class NotFoundView(APIView):
    """抛出 404。"""

    permission_classes = []

    def get(self, request):
        """抛出 Http404。"""
        raise Http404()


class UnexpectedErrorView(APIView):
    """抛出未捕获异常，用于验证不泄露内部信息。"""

    permission_classes = []

    def get(self, request):
        """抛出内部异常。"""
        raise RuntimeError('internal-secret-should-not-leak')


class AuthenticatedOnlyView(APIView):
    """需要认证。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """返回成功标记。"""
        return Response({'ok': True})


class AdminOnlyView(APIView):
    """需要管理员权限。"""

    permission_classes = [IsAdminUser]

    def get(self, request):
        """返回成功标记。"""
        return Response({'ok': True})


class ItemListView(APIView):
    """返回分页列表，用于验证分页契约。"""

    permission_classes = []

    def get(self, request):
        """返回分页后的数据。"""
        items = [{'id': index} for index in range(TOTAL_ITEMS)]
        paginator = StandardPagination()
        page = paginator.paginate_queryset(items, request, view=self)
        return paginator.get_paginated_response(page)


urlpatterns = [
    path('test/app-error', AppErrorView.as_view()),
    path('test/validation-error', ValidationErrorView.as_view()),
    path('test/not-found', NotFoundView.as_view()),
    path('test/unexpected', UnexpectedErrorView.as_view()),
    path('test/auth-required', AuthenticatedOnlyView.as_view()),
    path('test/admin-only', AdminOnlyView.as_view()),
    path('test/items', ItemListView.as_view()),
]
