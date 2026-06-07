"""Pytest-style tests for query views demonstrating coexistence with Django TestCase.

These tests exercise the same behaviour as ``queries/tests/test_views.py`` but
use pytest fixtures and plain functions instead of ``TestCase`` subclasses.
They can be run via::

    pytest policyiq/queries/tests/test_views_pytest.py -v

or alongside the full suite::

    pytest policyiq

Both ``manage.py test`` and ``pytest`` discover and run these tests successfully.
"""

import json
from unittest import mock
from uuid import uuid4

import pytest
from django.conf import settings
from django.test import RequestFactory

from queries.views import AskPageView

pytestmark = pytest.mark.django_db


@pytest.fixture
def ask_view():
    """Return an instantiated AskPageView callable (as_view)."""
    return AskPageView.as_view()


class TestAskPageViewGet:
    """Pytest equivalents of AskPageView GET tests."""

    def test_renders_form_with_documents(self, ask_view):

        dt = mock.Mock()
        doc1 = mock.Mock(id=uuid4(), uploaded_at=dt)
        doc1.name = "Policy A.pdf"
        doc2 = mock.Mock(id=uuid4(), uploaded_at=dt)
        doc2.name = "Policy B.pdf"

        with mock.patch("queries.views.Document.objects.order_by", return_value=[doc1, doc2]):
            factory = RequestFactory()
            request = factory.get("/ask/")
            response = ask_view(request)

        assert response.status_code == 200
        content = response.content.decode()
        assert "Ask a Question" in content
        assert "Policy A.pdf" in content
        assert "Policy B.pdf" in content
        assert 'hx-post="/ask/"' in content


class TestAskPageViewPost:
    """Pytest equivalents of AskPageView POST tests."""

    def test_empty_question_returns_400(self, ask_view):
        factory = RequestFactory()
        request = factory.post("/ask/", {"question": "   "})
        response = ask_view(request)

        assert response.status_code == 400
        assert "Please enter a question" in response.content.decode()

    @mock.patch("queries.views.run_query")
    def test_streams_answer_when_chunks_found(self, mock_run_query, ask_view):
        from queries.services.query_pipeline import QueryResult

        mock_run_query.return_value = QueryResult(
            kind="answer",
            answer_stream=iter(["Answer", " is", " yes."]),
            citations=[],
        )

        factory = RequestFactory()
        request = factory.post("/ask/", {"question": "Is it covered?"})
        response = ask_view(request)

        assert response.status_code == 200
        content = b"".join(response.streaming_content).decode("utf-8")
        assert content == '<div class="card"><p style="white-space: pre-wrap;">Answer is yes.</p></div>'
        mock_run_query.assert_called_once_with(
            "Is it covered?", None, top_k=settings.RETRIEVAL_TOP_K, threshold=settings.SIMILARITY_THRESHOLD
        )

    @mock.patch("queries.views.run_query")
    def test_returns_message_when_no_relevant_chunks(self, mock_run_query, ask_view):
        from queries.services.query_pipeline import QueryResult

        mock_run_query.return_value = QueryResult(kind="no_information")

        factory = RequestFactory()
        request = factory.post("/ask/", {"question": "Is it covered?"})
        response = ask_view(request)

        assert response.status_code == 200
        assert "No relevant information found" in response.content.decode()

    @mock.patch("queries.views.run_query")
    def test_passes_document_id_to_retriever(self, mock_run_query, ask_view):
        from queries.services.query_pipeline import QueryResult

        mock_run_query.return_value = QueryResult(
            kind="answer",
            answer_stream=iter(["Yes"]),
            citations=[],
        )

        factory = RequestFactory()
        request = factory.post(
            "/ask/",
            {"question": "Is it covered?", "document_id": "11111111-1111-1111-1111-111111111111"},
        )
        response = ask_view(request)

        assert response.status_code == 200
        mock_run_query.assert_called_once_with(
            "Is it covered?",
            "11111111-1111-1111-1111-111111111111",
            top_k=settings.RETRIEVAL_TOP_K,
            threshold=settings.SIMILARITY_THRESHOLD,
        )

    @mock.patch("queries.views.run_query")
    def test_includes_x_citations_header(self, mock_run_query, ask_view):
        from queries.services.query_pipeline import QueryResult

        citations = [
            {
                "document_name": "Policy.pdf",
                "page_number": 3,
                "similarity_score": 0.92,
                "text_preview": "Coverage is approved for this procedure."[:150],
            },
            {
                "document_name": "Policy.pdf",
                "page_number": 5,
                "similarity_score": 0.78,
                "text_preview": "PA not needed.",
            },
        ]
        mock_run_query.return_value = QueryResult(
            kind="answer",
            answer_stream=iter(["Yes"]),
            citations=citations,
        )

        factory = RequestFactory()
        request = factory.post("/ask/", {"question": "Is it covered?"})
        response = ask_view(request)

        assert response.status_code == 200
        assert "X-Citations" in response
        parsed = json.loads(response["X-Citations"])
        assert len(parsed) == 2
        assert parsed[0]["document_name"] == "Policy.pdf"
        assert parsed[0]["page_number"] == 3
        assert parsed[0]["similarity_score"] == 0.92
        assert parsed[0]["text_preview"] == "Coverage is approved for this procedure."[:150]
