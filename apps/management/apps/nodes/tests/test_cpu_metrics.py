from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.instances.tests.helpers import make_node, make_user
from apps.nodes.services import refresh_node
from apps.nodes.tests.fakes import FakeAgentClient


class CPUMetricTests(TestCase):
    def test_dashboard_weights_fresh_cpu_samples_and_hides_host_metrics_from_user(self):
        admin = make_user('cpu-admin', 'Admin')
        user = make_user('cpu-user', 'Viewer')
        now = timezone.now()
        make_node(
            name='cpu-a',
            cpu_total=2,
            cpu_usage_percent=10,
            cpu_sampled_at=now,
            resource_is_stale=False,
        )
        make_node(
            name='cpu-b',
            cpu_total=6,
            cpu_usage_percent=50,
            cpu_sampled_at=now,
            resource_is_stale=False,
        )
        make_node(
            name='cpu-stale',
            cpu_total=100,
            cpu_usage_percent=100,
            cpu_sampled_at=now,
            resource_is_stale=True,
        )
        make_node(
            name='cpu-old',
            cpu_total=100,
            cpu_usage_percent=100,
            cpu_sampled_at=now - timedelta(minutes=5),
            resource_is_stale=False,
        )
        self.client.force_login(admin)
        result = self.client.get('/api/v1/console/dashboard').json()
        self.assertEqual(result['cpu_percent'], 40)
        self.assertEqual(result['cpu_sampled_nodes'], 2)
        self.client.force_login(user)
        self.assertIsNone(self.client.get('/api/v1/console/dashboard').json()['cpu_percent'])

    def test_refresh_accepts_zero_and_discards_invalid_or_missing_samples(self):
        node = make_node(name='cpu-refresh')
        resources = FakeAgentClient().resources()
        resources.update(cpu_usage_percent=0, cpu_sampled_at=timezone.now().isoformat())
        refresh_node(node, client=FakeAgentClient(resources=resources))
        self.assertEqual(node.cpu_usage_percent, 0)
        self.assertIsNotNone(node.cpu_sampled_at)
        for value in [None, -1, 101, float('nan'), True]:
            resources['cpu_usage_percent'] = value
            refresh_node(node, client=FakeAgentClient(resources=resources))
            self.assertIsNone(node.cpu_usage_percent)
            self.assertIsNone(node.cpu_sampled_at)
        resources.update(
            cpu_usage_percent=20, cpu_sampled_at=(timezone.now() - timedelta(minutes=5)).isoformat()
        )
        refresh_node(node, client=FakeAgentClient(resources=resources))
        self.assertIsNone(node.cpu_usage_percent)
