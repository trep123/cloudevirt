"""分页契约测试。"""

from django.test import TestCase, override_settings


@override_settings(ROOT_URLCONF='common.tests.urls')
class PaginationTests(TestCase):
    """验证默认条数、上限收敛与响应结构。"""

    def test_default_page_size(self) -> None:
        """未指定 page_size 时使用默认条数。"""
        response = self.client.get('/test/items')

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['count'], 250)
        self.assertEqual(len(body['results']), 20)

    def test_page_size_is_clamped_to_maximum(self) -> None:
        """超出上限的 page_size 应被收敛到上限。"""
        response = self.client.get('/test/items?page_size=1000')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 100)

    def test_pagination_response_shape(self) -> None:
        """分页响应应包含 count/next/previous/results。"""
        response = self.client.get('/test/items?page=2&page_size=10')

        body = response.json()
        self.assertEqual(set(body), {'count', 'next', 'previous', 'results'})
        self.assertEqual(body['results'][0]['id'], 10)
        self.assertIsNotNone(body['previous'])
