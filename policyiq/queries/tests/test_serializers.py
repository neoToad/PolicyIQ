from uuid import uuid4

from django.test import SimpleTestCase

from queries.serializers import CitationSerializer, QueryRequestSerializer, QueryResponseSerializer


class QueryRequestSerializerTests(SimpleTestCase):
    def test_valid_question(self):
        serializer = QueryRequestSerializer(data={"question": "What is the policy?"})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["question"], "What is the policy?")

    def test_blank_question_is_invalid(self):
        serializer = QueryRequestSerializer(data={"question": "   "})
        self.assertFalse(serializer.is_valid())
        self.assertIn("question", serializer.errors)

    def test_missing_question_is_invalid(self):
        serializer = QueryRequestSerializer(data={})
        self.assertFalse(serializer.is_valid())
        self.assertIn("question", serializer.errors)

    def test_optional_document_id(self):
        doc_id = uuid4()
        serializer = QueryRequestSerializer(data={"question": "Hello", "document_id": str(doc_id)})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["document_id"], doc_id)

    def test_null_document_id_is_allowed(self):
        serializer = QueryRequestSerializer(data={"question": "Hello", "document_id": None})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertIsNone(serializer.validated_data["document_id"])


class CitationSerializerTests(SimpleTestCase):
    def test_citation_fields(self):
        data = {
            "document_name": "policy.pdf",
            "page_number": 3,
            "similarity_score": 0.85,
            "text_preview": "This is a preview...",
        }
        serializer = CitationSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["document_name"], "policy.pdf")
        self.assertEqual(serializer.validated_data["similarity_score"], 0.85)

    def test_optional_page_number(self):
        data = {
            "document_name": "policy.pdf",
            "similarity_score": 0.85,
            "text_preview": "Preview",
        }
        serializer = CitationSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertIsNone(serializer.validated_data.get("page_number"))


class QueryResponseSerializerTests(SimpleTestCase):
    def test_query_response_with_citations(self):
        data = {
            "answer": "The policy covers...",
            "citations": [
                {
                    "document_name": "policy.pdf",
                    "page_number": 2,
                    "similarity_score": 0.92,
                    "text_preview": "Coverage includes...",
                }
            ],
        }
        serializer = QueryResponseSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["answer"], "The policy covers...")
        self.assertEqual(len(serializer.validated_data["citations"]), 1)
