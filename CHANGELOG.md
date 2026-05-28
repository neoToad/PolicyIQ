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

### [Phase2.5] Query smoke test
- Added `test_query.py` standalone script for manual end-to-end pipeline validation
- Configurable question and optional document_id at the top
- Prints retrieved chunks with similarity scores, page numbers, and previews
- Prints the full built prompt before streaming
- Streams generate_response token by token to stdout

---

## Phase 3 — HTMX Frontend

### [Phase3.1] Base template
- Created `templates/base.html` with HTMX CDN, minimal CSS, and top nav
- Styled as a professional internal tool: neutral colors, high contrast, no decoration
- Added stub page views (`UploadPageView`, `HistoryPageView`, `AskPageView`) so nav links resolve
- Wired page URLs into root `urls.py` with named routes (`upload-page`, `history-page`, `ask-page`)
- Added placeholder templates for upload, history, and ask pages to prevent 404s

### [Phase3.2] Upload form
- Rewrote `templates/documents/upload.html` with HTMX file upload form (PDF-only, multipart encoding)
- Added `templates/documents/_upload_result.html` partial for success/error feedback swapped by HTMX
- Updated `UploadPageView` to handle POST and return HTML partials instead of JSON
- Refactored ingestion pipeline into `_save_upload_and_ingest()` shared by page view and API view

### [Phase3.3] Upload history
- Updated `HistoryPageView` to fetch all documents ordered by upload date
- Added `DocumentDeleteView` that removes a document from PostgreSQL and ChromaDB
- Wired delete URL at `/documents/<uuid>/delete/`
- Rewrote `templates/documents/history.html` with a table and HTMX delete buttons
- Delete buttons use `hx-confirm`, `hx-target` on the row, and `outerHTML` swap for smooth removal

### [Phase3.4] Question input
- Updated `AskPageView` to handle GET (documents dropdown) and POST (query pipeline)
- Rewrote `templates/queries/ask.html` with HTMX form: textarea, document selector, loading indicator
- POST returns HTML partials or a StreamingHttpResponse with HTML-wrapped tokens
- Preserves X-Citations header for the citations panel in step 3.5

### [Phase3.5] Citations panel
- Added `#citations` div below `#answer` in `templates/queries/ask.html`
- JavaScript listens to `htmx:afterRequest`, reads `X-Citations` header, and renders a sources card
- Each citation shows document name, page number, similarity score as a percentage, and a 150-char preview
- Panel is hidden when no citations are present (e.g., low-similarity or error responses)

---

## Phase 4 — Polish


