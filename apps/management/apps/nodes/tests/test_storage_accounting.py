from django.test import TestCase

from apps.nodes.models import Node
from apps.nodes.services import refresh_node
from apps.nodes.tests.fakes import FakeAgentClient


class StorageAccountingTests(TestCase):
    def test_shared_filesystem_is_counted_once_and_legacy_agent_still_works(self):
        node = Node.objects.create(name='disk-accounting', endpoint='http://localhost:9100')
        resources = {
            'cpu_logical': 4,
            'memory_total_mib': 4096,
            'memory_available_mib': 2048,
            'storage': [
                {'path': '/images', 'filesystem_id': '8', 'total_bytes': 1000, 'free_bytes': 500},
                {'path': '/disks', 'filesystem_id': '8', 'total_bytes': 1000, 'free_bytes': 490},
                {'path': '/other', 'filesystem_id': '9', 'total_bytes': 2000, 'free_bytes': 1000},
            ],
        }
        refresh_node(node, client=FakeAgentClient(resources=resources))
        self.assertEqual(node.storage_total_bytes, 3000)
        self.assertEqual(node.storage_free_bytes, 1490)
        for item in resources['storage']:
            item.pop('filesystem_id')
        refresh_node(node, client=FakeAgentClient(resources=resources))
        self.assertEqual(node.storage_total_bytes, 4000)
