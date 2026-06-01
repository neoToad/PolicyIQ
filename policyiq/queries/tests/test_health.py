from unittest import mock

from django.test import SimpleTestCase, override_settings

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
    @override_settings(OLLAMA_BASE_URL="http://ollama-host:11434")
    @mock.patch("queries.services.health.requests.get")
    def test_returns_up_when_api_tags_responds(self, mock_get):
        mock_get.return_value.raise_for_status.return_value = None

        result = health.check_ollama()

        self.assertEqual(result, {"status": "up"})
        mock_get.assert_called_once_with("http://ollama-host:11434/api/tags", timeout=2.0)

    @override_settings(OLLAMA_BASE_URL="http://ollama-host:11434/")
    @mock.patch("queries.services.health.requests.get")
    def test_strips_trailing_slash_from_base_url(self, mock_get):
        mock_get.return_value.raise_for_status.return_value = None

        health.check_ollama()

        called_url = mock_get.call_args.args[0]
        self.assertEqual(called_url, "http://ollama-host:11434/api/tags")

    @mock.patch("queries.services.health.requests.get")
    def test_returns_down_with_error_when_request_fails(self, mock_get):
        mock_get.side_effect = ConnectionError("refused")

        result = health.check_ollama()

        self.assertEqual(result["status"], "down")
        self.assertIn("refused", result["error"])

    @mock.patch("queries.services.health.requests.get")
    def test_returns_down_when_status_is_not_ok(self, mock_get):
        response = mock.Mock()
        response.raise_for_status.side_effect = RuntimeError("500")
        mock_get.return_value = response

        result = health.check_ollama()

        self.assertEqual(result["status"], "down")
        self.assertIn("500", result["error"])
