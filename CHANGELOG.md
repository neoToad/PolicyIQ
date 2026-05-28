# PolicyIQ Build Changelog

## Phase 1 — Completed (pre-existing)
- 1.1 Project Scaffolding
- 1.2 Django Models
- 1.3 PDF Raw Extraction
- 1.4 PDF Text Cleanup
- 1.5 Chunker
- 1.6 Embedder
- 1.7 ChromaDB Indexer
- 1.8 Ingestion View
- 1.9 Ingestion Smoke Test

All Phase 1 steps were already implemented and committed on main before the feature branch was created.

---

## Phase 2 — Query Interface

### [Phase2.1] Retriever service
- Built queries/services/retriever.py with etrieve_chunks()
- Added unit tests in queries/tests/test_services.py
- Fetches query embedding, queries ChromaDB, optionally filters by document, returns scored/ordered results

### [Phase2.2] Prompt builder
- Built uild_prompt() in queries/services/generator.py
- Added threshold-based guard that returns None when no chunk is relevant enough
- Constructed grounded prompt with document name, page number, and chunk text per citation
- Added retriever refactor to enrich chunks with document_name from PostgreSQL

### [Phase2.3] Generator
- Added generate_response() generator to queries/services/generator.py
- Streams Ollama generate API line-by-line with equests streaming
- Retry logic (3 attempts) with clear RuntimeError on unreachable service
- Added unit tests for streaming, retry success, and unreachable failure

### [Phase2.4] Query view
- Built QueryAPIView in queries/views.py as a DRF APIView
- Wires etrieve_chunks -> uild_prompt -> generate_response
- Returns StreamingHttpResponse with plain text when chunks are relevant
- Returns JSON {'answer': 'No relevant information found...'} when prompt is None
- Adds X-Citations header with document name, page number, score, and text preview
- Created queries/urls.py and wired into root urls.py
- Added comprehensive view tests for streaming, no-results, document filter, and citations header
