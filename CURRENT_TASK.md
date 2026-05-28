# Current Task

**Step 2.5 — Query Smoke Test**

Writing `test_query.py` for PolicyIQ.

- Standalone script (not a Django test) for manual end-to-end pipeline validation
- Configurable question string and optional document_id at the top
- Calls retrieve_chunks, prints each chunk with score and page number
- Calls build_prompt and prints the full prompt
- Calls generate_response and prints streamed output token by token

Next: Phase 3 — HTMX Frontend (3.1 Base Template).