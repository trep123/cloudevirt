"""Production health checks must retain the configured local host allowlist."""
from django.test import SimpleTestCase, override_settings


class HostConfigurationTests(SimpleTestCase):
    @override_settings(DEBUG=False)
    def test_local_health_endpoint_is_allowed_with_debug_disabled(self):
        response = self.client.get('/api/v1/health', HTTP_HOST='127.0.0.1')
        self.assertEqual(response.status_code, 200)
