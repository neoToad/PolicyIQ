"""Tests for the `queries.retriever` logger.

The chunk-list log line is the highest-leverage change in the logging
build: it answers "did the LLM see the right chunks?" by emitting
`Chunks: [docname p.N (score), ...]`. These tests lock the diagnostic
format in place so future refactors can't silently drop or change it.
"""

from unittest import mock

from django.test import SimpleTestCase

from queries.constants import MAX_QUESTION_LOG_CHARS
from queries.services.retriever import (
    MAX_CHUNKS_IN_LOG,
    retrieve_chunks,
)


def _mock_chroma_result():
    """Return a mock ChromaDB query() response with 2 chunks."""
    return {
        "ids": [["doc-1:0", "doc-1:50"]],
        "documents": [["first chunk text", "second chunk text"]],
        "metadatas": [
            [
                {
                    "document_id": "doc-1",
                    "document_name": "Test Policy.pdf",
                    "page_number": 1,
                    "token_offset": 0,
                },
                {
                    "document_id": "doc-1",
                    "document_name": "Test Policy.pdf",
                    "page_number": 2,
                    "token_offset": 50,
                },
            ]
        ],
        "distances": [[0.2, 0.5]],
    }


class RetrieverLoggingTests(SimpleTestCase):
    @mock.patch("queries.services.retriever.get_collection")
    @mock.patch("queries.services.retriever.embed_query")
    def test_retriever_logs_chunk_ids_and_scores(self, mock_embed_query, mock_get_collection):
        """The 'Chunks: [...]' line is the diagnostic contract — must list
        document name, page number, and similarity score for each chunk."""
        mock_embed_query.return_value = [0.1, 0.2, 0.3]
        mock_collection = mock.Mock()
        mock_collection.query.return_value = _mock_chroma_result()
        mock_get_collection.return_value = mock_collection

        with self.assertLogs("queries.retriever", level="INFO") as cm:
            retrieve_chunks("test question", top_k=5)

        # Find the "Chunks: [...]" line.
        chunk_lines = [line for line in cm.output if "Chunks:" in line]
        self.assertEqual(len(chunk_lines), 1, f"Expected one Chunks: line, got: {cm.output}")
        chunk_line = chunk_lines[0]
        # Document name and page numbers must appear in the formatted line.
        self.assertIn("Test Policy.pdf", chunk_line)
        self.assertIn("p.1", chunk_line)
        self.assertIn("p.2", chunk_line)
        # Similarity scores must appear (formatted to 3 decimals).
        self.assertIn("0.900", chunk_line)  # first chunk score
        self.assertIn("0.750", chunk_line)  # second chunk score
        # PII guard: the chunk TEXT must NOT appear in the log line.
        self.assertNotIn("first chunk text", chunk_line)
        self.assertNotIn("second chunk text", chunk_line)

    @mock.patch("queries.services.retriever.get_collection")
    @mock.patch("queries.services.retriever.embed_query")
    def test_retriever_logs_embed_and_retrieve_durations(self, mock_embed_query, mock_get_collection):
        """Both timing lines (embed, retrieve) must be emitted with non-negative durations."""
        mock_embed_query.return_value = [0.1, 0.2, 0.3]
        mock_collection = mock.Mock()
        mock_collection.query.return_value = _mock_chroma_result()
        mock_get_collection.return_value = mock_collection

        with self.assertLogs("queries.retriever", level="INFO") as cm:
            retrieve_chunks("test question", top_k=5)

        embed_lines = [line for line in cm.output if "Embedded query" in line]
        retrieve_lines = [line for line in cm.output if "Retrieved " in line and "from " in line]
        self.assertEqual(len(embed_lines), 1)
        self.assertEqual(len(retrieve_lines), 1)
        # Each line should include "in T.TTs" suffix.
        self.assertIn("in ", embed_lines[0])
        self.assertIn("in ", retrieve_lines[0])

    @mock.patch("queries.services.retriever.get_collection")
    @mock.patch("queries.services.retriever.embed_query")
    def test_retriever_logs_zero_chunks(self, mock_embed_query, mock_get_collection):
        """Empty-results path emits 'Retrieved 0 chunks' — NOT the Chunks: line."""
        mock_embed_query.return_value = [0.1, 0.2, 0.3]
        mock_collection = mock.Mock()
        mock_collection.query.return_value = {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }
        mock_get_collection.return_value = mock_collection

        with self.assertLogs("queries.retriever", level="INFO") as cm:
            retrieve_chunks("test question", top_k=5)

        # "Retrieved 0 chunks" line is present.
        zero_lines = [line for line in cm.output if "Retrieved 0 chunks" in line]
        self.assertEqual(len(zero_lines), 1)
        # "Chunks: [...]" line is NOT present (would be misleading for zero results).
        chunk_lines = [line for line in cm.output if "Chunks:" in line]
        self.assertEqual(len(chunk_lines), 0)

    @mock.patch("queries.services.retriever.get_collection")
    @mock.patch("queries.services.retriever.embed_query")
    def test_retriever_logs_question_truncated_to_max_chars(self, mock_embed_query, mock_get_collection):
        """Long questions are truncated to MAX_QUESTION_LOG_CHARS for the
        'Retrieving up to N chunks' line — protects PII / log volume."""
        mock_embed_query.return_value = [0.1, 0.2, 0.3]
        mock_collection = mock.Mock()
        mock_collection.query.return_value = _mock_chroma_result()
        mock_get_collection.return_value = mock_collection

        long_question = "x" * (MAX_QUESTION_LOG_CHARS + 50)
        with self.assertLogs("queries.retriever", level="INFO") as cm:
            retrieve_chunks(long_question, top_k=5)

        # The receipt line must include the "..." truncation marker.
        receipt_lines = [line for line in cm.output if "Retrieving up to" in line]
        self.assertEqual(len(receipt_lines), 1)
        self.assertIn("...", receipt_lines[0])
        # And it must NOT include the full long text.
        self.assertNotIn("x" * (MAX_QUESTION_LOG_CHARS + 50), receipt_lines[0])

    @mock.patch("queries.services.retriever.get_collection")
    @mock.patch("queries.services.retriever.embed_query")
    def test_retriever_logs_retrieve_summary_with_score_range(self, mock_embed_query, mock_get_collection):
        """The 'Retrieved N chunks from M documents' line includes the score range
        and a duration — the operator's answer to 'was retrieval slow? was relevance OK?'"""
        mock_embed_query.return_value = [0.1, 0.2, 0.3]
        mock_collection = mock.Mock()
        mock_collection.query.return_value = _mock_chroma_result()
        mock_get_collection.return_value = mock_collection

        with self.assertLogs("queries.retriever", level="INFO") as cm:
            retrieve_chunks("test question", top_k=5)

        summary_lines = [line for line in cm.output if "Retrieved 2 chunks" in line and "from 1 documents" in line]
        self.assertEqual(len(summary_lines), 1, f"Expected one summary line, got: {cm.output}")
        # top=0.900, range 0.750-0.900 (max - min)
        self.assertIn("top=0.900", summary_lines[0])
        self.assertIn("0.750-0.900", summary_lines[0])

    @mock.patch("queries.services.retriever.get_collection")
    @mock.patch("queries.services.retriever.embed_query")
    def test_retriever_chunks_log_caps_at_max_with_more_suffix(self, mock_embed_query, mock_get_collection):
        """When top_k > MAX_CHUNKS_IN_LOG, the chunk-list line caps at MAX and adds
        a '+N more' suffix — log volume protection."""
        mock_embed_query.return_value = [0.1, 0.2, 0.3]
        # Generate 12 chunks (more than the cap of 10) with decreasing scores.
        n_chunks = MAX_CHUNKS_IN_LOG + 2
        ids = [[f"doc-1:{i}" for i in range(n_chunks)]]
        documents = [[f"chunk {i}" for i in range(n_chunks)]]
        metadatas = [
            [
                {
                    "document_id": "doc-1",
                    "document_name": "P.pdf",
                    "page_number": i + 1,
                    "token_offset": i,
                }
                for i in range(n_chunks)
            ]
        ]
        # Decreasing squared L2 distance => decreasing similarity
        distances = [[i * 0.2 for i in range(n_chunks)]]
        mock_collection = mock.Mock()
        mock_collection.query.return_value = {
            "ids": ids,
            "documents": documents,
            "metadatas": metadatas,
            "distances": distances,
        }
        mock_get_collection.return_value = mock_collection

        with self.assertLogs("queries.retriever", level="INFO") as cm:
            retrieve_chunks("test question", top_k=n_chunks)

        chunk_lines = [line for line in cm.output if "Chunks:" in line]
        self.assertEqual(len(chunk_lines), 1)
        chunk_line = chunk_lines[0]
        # "+N more" suffix must be present.
        self.assertIn(f"+{n_chunks - MAX_CHUNKS_IN_LOG} more", chunk_line)
