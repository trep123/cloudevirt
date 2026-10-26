"""统一分页器。"""

from django.conf import settings
from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """列表接口统一分页器。

    - 页码参数：page
    - 每页条数参数：page_size，受 settings.API_MAX_PAGE_SIZE 上限约束
    """

    page_query_param = 'page'
    page_size_query_param = 'page_size'
    page_size = 20

    def get_page_size(self, request) -> int:
        """返回本次请求的每页条数，超出上限时收敛到上限。

        Args:
            request: 当前请求。

        Returns:
            实际使用的每页条数。
        """
        max_page_size = getattr(settings, 'API_MAX_PAGE_SIZE', 100)
        requested = super().get_page_size(request)
        return min(requested, max_page_size)
