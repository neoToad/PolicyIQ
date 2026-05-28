# Current Task

**Step 2.4 — Query View**

Building queries/views.py for PolicyIQ.

- Implementing a DRF APIView that:
  - Accepts POST with question and optional document_id
  - Runs etrieve_chunks -> uild_prompt -> generate_response
  - Returns JSON with {'answer': 'No relevant information found...'} when prompt is None
  - Returns StreamingHttpResponse for successful generations
  - Adds X-Citations header with serialized chunk metadata

Next: 2.5 — Query Smoke Test.
