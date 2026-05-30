import json
from unittest import mock

from django.test import SimpleTestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from queries.views import QueryAPIView


class QueryAPIViewTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = QueryAPIView.as_view()
        self.user = mock.Mock()
        self.user.is_authenticated = True

    @mock.patch("queries.views.generate_response")
    @mock.patch("queries.views.build_prompt")
    @mock.patch("queries.views.retrieve_chunks")
    def test_query_returns_streaming_response_when_chunks_found(
        self, mock_retrieve, mock_build_prompt, mock_generate
    ):
        chunks = [
            {"text": "Coverage yes.", "page_number": 2, "document_name": "Policy.pdf", "similarity_score": 0.85},
        ]
        mock_retrieve.return_value = chunks
        mock_build_prompt.return_value = "prompt text"
        mock_generate.return_value = iter(["Answer", " is", " yes."])

        request = self.factory.post("/api/queries/", {"question": "Is it covered?"})
        force_authenticate(request, user=self.user)
        response = self.view(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = b"".join(response.streaming_content).decode("utf-8")
        self.assertEqual(content, "Answer is yes.")
        mock_retrieve.assert_called_once_with("Is it covered?", document_id=None, top_k=5)
        mock_build_prompt.assert_called_once_with("Is it covered?", chunks, similarity_threshold=0.5)
        mock_generate.assert_called_once_with("prompt text")

    @mock.patch("queries.views.generate_response")
    @mock.patch("queries.views.build_prompt")
    @mock.patch("queries.views.retrieve_chunks")
    def test_query_returns_json_when_no_relevant_chunks(
        self, mock_retrieve, mock_build_prompt, mock_generate
    ):
        mock_retrieve.return_value = []
        mock_build_prompt.return_value = None

        request = self.factory.post("/api/queries/", {"question": "Is it covered?"})
        force_authenticate(request, user=self.user)
        response = self.view(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["answer"], "No relevant information found in the uploaded documents.")
        mock_generate.assert_not_called()

    @mock.patch("queries.views.generate_response")
    @mock.patch("queries.views.build_prompt")
    @mock.patch("queries.views.retrieve_chunks")
    def test_query_passes_document_id_to_retriever(
        self, mock_retrieve, mock_build_prompt, mock_generate
    ):
        chunks = [
            {"text": "Coverage yes.", "page_number": 2, "document_name": "Policy.pdf", "similarity_score": 0.85},
        ]
        mock_retrieve.return_value = chunks
        mock_build_prompt.return_value = "prompt text"
        mock_generate.return_value = iter(["Yes"])

        request = self.factory.post(
            "/api/queries/",
            {"question": "Is it covered?", "document_id": "11111111-1111-1111-1111-111111111111"},
        )
        force_authenticate(request, user=self.user)
        response = self.view(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_retrieve.assert_called_once_with(
            "Is it covered?", document_id="11111111-1111-1111-1111-111111111111", top_k=5
        )

    @mock.patch("queries.views.generate_response")
    @mock.patch("queries.views.build_prompt")
    @mock.patch("queries.views.retrieve_chunks")
    def test_query_includes_x_citations_header(
        self, mock_retrieve, mock_build_prompt, mock_generate
    ):
        chunks = [
            {"text": "Coverage is approved for this procedure.", "page_number": 3, "document_name": "Policy.pdf", "similarity_score": 0.92},
            {"text": "PA not needed.", "page_number": 5, "document_name": "Policy.pdf", "similarity_score": 0.78},
        ]
        mock_retrieve.return_value = chunks
        mock_build_prompt.return_value = "prompt text"
        mock_generate.return_value = iter(["Yes"])

        request = self.factory.post("/api/queries/", {"question": "Is it covered?"})
        force_authenticate(request, user=self.user)
        response = self.view(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("X-Citations", response)
        citations = json.loads(response["X-Citations"])
        self.assertEqual(len(citations), 2)
        self.assertEqual(citations[0]["document_name"], "Policy.pdf")
        self.assertEqual(citations[0]["page_number"], 3)
        self.assertEqual(citations[0]["similarity_score"], 0.92)
        self.assertEqual(citations[0]["text_preview"], "Coverage is approved for this procedure."[:150])
