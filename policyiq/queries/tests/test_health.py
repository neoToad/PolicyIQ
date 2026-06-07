from unittest import mock

from django.test import SimpleTestCase

from queries.services import health


class CheckPostgreSQLTests(SimpleTestCase):
    @mock.patch("queries.services.health.connection")
    def test_returns_up_when_select_one_succeeds(self, mock_connection):
        mock_cursor = mock_connection.cursor.return_value.__enter__.return_value
        mock_cursor.fetchone.return_value = (1,)

        result = health.check_postgresql()

        self.assertEqual(result, {"status": "up"})
        mock_cursor.execute.assert_called_once_with("SELECT 1")

    @mock.patch("queries.services.health.connection")
    def test_returns_down_with_error_when_query_fails(self, mock_connection):
        mock_connection.cursor.return_value.__enter__.side_effect = RuntimeError("db down")

        result = health.check_postgresql()

        self.assertEqual(result["status"], "down")
        self.assertIn("db down", result["error"])


class CheckChromaDBTests(SimpleTestCase):
    def test_returns_up_when_get_collection_succeeds(self):
        result = health.check_chromadb(lambda: None)
        self.assertEqual(result, {"status": "up"})

    def test_returns_down_with_error_when_get_collection_fails(self):
        def boom():
            raise RuntimeError("chroma locked")

        result = health.check_chromadb(boom)

        self.assertEqual(result["status"], "down")
        self.assertIn("chroma locked", result["error"])


class CheckOllamaTests(SimpleTestCase):
    @mock.patch("queries.services.health.ollama.ping")
    def test_returns_up_when_ping_succeeds(self, mock_ping):
        mock_ping.return_value = True

        result = health.check_ollama()

        self.assertEqual(result, {"status": "up"})
        mock_ping.assert_called_once_with()

    @mock.patch("queries.services.health.ollama.ping")
    def test_returns_down_with_error_when_ping_fails(self, mock_ping):
        mock_ping.return_value = False

        result = health.check_ollama()

        self.assertEqual(result["status"], "down")
        self.assertEqual(result["error"], "Ollama unreachable")


class HealthOllamaClientTests(SimpleTestCase):
    """After Phase 0.2e, the health check must delegate to policyiq.ollama,
    not talk to requests directly. These tests pin the new boundary."""

    def test_health_does_not_import_requests(self):
        import queries.services.health as health_mod

        self.assertFalse(hasattr(health_mod, "requests"))

    def test_health_imports_ollama_client(self):
        import queries.services.health as health_mod

        self.assertTrue(hasattr(health_mod, "ollama"))
