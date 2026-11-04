import unittest

from backend.main import health_check


class HealthEndpointTests(unittest.TestCase):
    def test_health_endpoint_reports_service(self):
        coroutine = health_check()
        try:
            coroutine.send(None)
        except StopIteration as result:
            response = result.value

        self.assertEqual(
            response,
            {"status": "healthy", "service": "voice-agent-backend"},
        )


if __name__ == "__main__":
    unittest.main()
