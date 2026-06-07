# PolicyIQ Refactor Audit

A prioritized review of the PolicyIQ codebase, scoped to the seven categories requested: service layer boundaries, hardcoded config, error handling, duplication, ChromaDB coupling, Django model usage, streaming response handling, and test coverage gaps. Findings are organized by priority (High / Medium / Low) and are read-only — no code changes are proposed in this document.

---

## High — Pipeline failure leaves orphaned `Chunk` records when ChromaDB write fails
**File:** `policyiq/documents/services/pipeline.py:57-69`
**Issue:** `Chunk.objects.bulk_create(...)` runs **before** `index_document(...)`. If the ChromaDB call subsequently raises (`IndexingError` / `RuntimeError`), the partial side effects are:
1. PostgreSQL has the chunk rows committed (autocommit, no `transaction.atomic`).
2. `Document.page_count` and `Document.chunk_count` are already saved.
3. The temp `Document` row is deleted in the view layer's `except` block, which cascades to `Chunk` rows because `on_delete=CASCADE` is configured — so in the *upload* view this is recovered. But `StaffDocumentReindexView.post` (`policyiq/documents/views.py:244-257`) calls `ingest_document(document)` directly with no rollback, so a reindex that fails at the index stage leaves orphan `Chunk` rows for the same `document_id` from the *prior* reindex (or any earlier successful run). The `Chunk.objects.filter(document=document).delete()` call before reindex is best-effort and runs before the pipeline, but if the prior run partially wrote rows the new run could collide on the UUID primary key.
4. The pipeline's `try/except` at `pipeline.py:36-106` re-raises without rolling back the `bulk_create` because there is no enclosing transaction.
**Fix:** Wrap the PG write + ChromaDB write in `transaction.atomic()` and add a compensating `Chunk.objects.filter(document=document).delete()` + `index_document` delete in the pipeline's `except` block (or have the indexer accept a list of already-written chunk UUIDs to roll back). At minimum, run `bulk_create` *after* `index_document` succeeds, so a ChromaDB failure leaves the PG side clean. Also re-test the reindex path against partial failure.

## High — `DocumentDeleteView` and `StaffDocumentDeleteView` reverse-delete order is non-atomic
**File:** `policyiq/documents/views.py:200-211` and `policyiq/documents/views.py:225-237`
**Issue:** Both views call `delete_document(str(document.id))` (ChromaDB) *before* `document.delete()` (PostgreSQL). If the PG delete fails, ChromaDB chunks are already gone — silent data loss. If the ChromaDB delete fails, the PG record is preserved and the chunks stay orphaned in the vector store. There is no `transaction.atomic()` and no compensation path. The `_save_upload_and_ingest` path (views.py:101-115) has a *similar* issue: if `default_storage.delete(temp_path)` fails after `document.delete()`, you get a leaked temp file, but that is lower-stakes.
**Fix:** Extract a `delete_document_with_chunks(document)` service in `documents/services/` that uses `transaction.atomic()`, calls ChromaDB delete first inside the transaction, and only commits the PG delete on success. On ChromaDB failure, log + raise without touching PG. On PG failure, attempt to restore the ChromaDB chunks (or at minimum, mark the document as "vector orphan" for a sweeper job).

## High — Hardcoded model names, URLs, and tunables in service modules
**File:** `policyiq/documents/services/embedder.py:10-14`, `policyiq/queries/services/generator.py:18-21, 52-53`
**Issue:** `OLLAMA_EMBED_URL = "http://localhost:11434/api/embed"`, `OLLAMA_EMBED_MODEL = "nomic-embed-text"`, `OLLAMA_GENERATE_URL = "http://localhost:11434/api/generate"`, `OLLAMA_GENERATE_MODEL = "llama3.2"`, `ANTHROPIC_MODEL = "claude-sonnet-4-20250514"`, `ANTHROPIC_MAX_TOKENS = 1024`, `RETRY_ATTEMPTS = 3`, `RETRY_DELAY_SECONDS = 1`, `DEFAULT_BATCH_SIZE = 32` are all module-level constants. The settings module already exposes `OLLAMA_BASE_URL` and `LLM_BACKEND`, but the URL is *not* used in either service — it is dead config. `chunk_size=500`, `overlap=50` defaults on `chunk_pages` (`chunker.py:9`) and `top_k=5` defaults in `retriever.py:27` and `views.py:25` are duplicated. The similarity threshold `0.5` is hardcoded in `views.py:53,101` and in `generator.build_prompt`'s default (`generator.py:130`), and the threshold-colored bar in `templates/queries/ask.html:69` re-encodes the same `0.5/0.75` boundary — the template can't know about settings.
**Fix:** Move every tunable to `settings.py` with sensible env-var defaults:
- `OLLAMA_EMBED_URL`, `OLLAMA_GENERATE_URL` (or one `OLLAMA_BASE_URL` plus a route builder in a shared `ollama_client.py`).
- `OLLAMA_EMBED_MODEL`, `OLLAMA_GENERATE_MODEL`, `ANTHROPIC_MODEL`, `ANTHROPIC_MAX_TOKENS`.
- `EMBEDDING_RETRY_ATTEMPTS`, `EMBEDDING_RETRY_DELAY`, `EMBEDDING_BATCH_SIZE`.
- `CHUNK_SIZE`, `CHUNK_OVERLAP`, `RETRIEVAL_TOP_K`, `SIMILARITY_THRESHOLD`.
Then have services do `getattr(settings, "OLLAMA_EMBED_MODEL", "nomic-embed-text")` (or pure `settings.X` reads in a small loader). Surface `SIMILARITY_THRESHOLD` to the template via a context processor so the JS bar's color boundaries stay in sync.

## High — Duplicated Ollama HTTP call pattern in `embedder.py` and `generator.py`
**File:** `policyiq/documents/services/embedder.py:54-117` and `policyiq/queries/services/generator.py:24-49`
**Issue:** Both files implement the same pattern: `requests.post(URL, json=payload, timeout=N)` with a `RETRY_ATTEMPTS=3` / `RETRY_DELAY_SECONDS=1` loop that catches `requests.RequestException` and `ValueError` / `json.JSONDecodeError`, and raises a domain-specific `EmbeddingError` / `GenerationError`. The batch and single-shot embedders in `embedder.py` are also near-identical (`_embed_batch_with_retry` vs `_embed_single_with_retry`) — the only differences are the `input` shape (list vs string) and the timeout (60 vs 30 s). Any change to retry policy, timeout handling, error mapping, or transport (e.g. switching to `httpx`) must be done in two places.
**Fix:** Create `documents/services/ollama_client.py` (or a top-level `services/ollama_client.py` if you want to share with `queries`) with:
- `post_json(path, payload, *, timeout)` — single POST with the shared retry loop, returning parsed JSON or raising `OllamaError`.
- `post_stream(path, payload, *, timeout)` — streaming variant for `/api/generate` that yields decoded JSON lines.
- `embed_texts(model, texts)` and `embed_query(model, text)` thin wrappers.
Have `embedder.py` and `generator.py` call into the client and only handle their own response-shape concerns. This also lets the health check (`queries/services/health.py:39-48`) use the same client for `GET /api/tags`.

## High — `QueryAPIView` and `AskPageView` duplicate the entire retrieve → prompt → stream pipeline
**File:** `policyiq/queries/views.py:36-75` and `policyiq/queries/views.py:84-126`
**Issue:** Both views repeat the same 4-step body: extract question + document_id, log "Query received", call `retrieve_chunks` + `build_prompt`, return either the "no relevant information" branch or build a `StreamingHttpResponse` wrapping `generate_response` with `X-Citations` header. They differ only in (a) input source (`request.POST` vs `request_serializer.validated_data`), (b) the "no chunks" response shape (HTML paragraph vs `Response` with `answer` field), and (c) the streaming body wrapper (HTML `<div>` vs plain text). The two implementations have already drifted — `similarity_threshold=0.5` is duplicated on lines 53 and 101.
**Fix:** Extract `queries/services/query_pipeline.py::run_query(question, document_id, top_k, threshold) -> QueryResult` returning either a "no relevant information" sentinel or a streaming token iterator plus citations. Both views become thin adapters that call `run_query()` and format the response. This also makes the streaming-response test surface one place instead of two (see "Test coverage" findings below).

## High — `generate_response` streams but errors during streaming are not surfaced to HTMX
**File:** `policyiq/queries/services/generator.py:104-127`, used in `policyiq/queries/views.py:62-75` and `policyiq/queries/views.py:115-118`
**Issue:** `generate_response` is a generator that yields tokens. If the underlying `_generate_ollama` raises `GenerationError` after some tokens have already been yielded, the `StreamingHttpResponse` will surface a truncated 500 to the client (Django's default behavior for a generator that raises mid-stream), and HTMX will display a partial answer with no error indicator. The view layer has no `try/except` around the streaming body and no error envelope. The `X-Citations` header is set *before* streaming starts, so the client gets citations even if the stream fails on the first token.
**Fix:** Wrap the generator with a small adapter that catches `GenerationError` / `RetrievalError`, yields a structured error marker (e.g. a closing `</div>` plus a `<!-- error: ollama unreachable -->` sentinel), and logs the error. Alternatively, use `StreamingHttpResponse` with a server-sent event format so HTMX can distinguish stream-end from stream-error. Add an integration test that mocks `_generate_ollama` to raise mid-stream and asserts the response is still well-formed HTML with an error indicator visible to the client.

## High — No integration test for "Ollama down at query time"
**File:** `policyiq/queries/tests/` (gap), `policyiq/queries/services/generator.py:24-49`
**Issue:** The unit tests cover the ollama-unreachable branch for `generate_response` (`test_generate_response_raises_clear_error_when_ollama_unreachable`, `test_services.py:196-204`) and for `embed_chunks` / `embed_query` (`test_services.py:198-205`). But there is no end-to-end test that drives the full `AskPageView` or `QueryAPIView` with Ollama down and asserts the user-facing response (status code, body content) is sane. The current unit tests assert the exception bubbles — the views' actual behavior under that exception is unverified, which is exactly the situation a production user would hit if Ollama restarts mid-day.
**Fix:** Add `QueryAPIViewOllamaDownTests` that patches `queries.services.generator.requests.post` to `raise requests.RequestException` for every call, drives a `POST /api/queries/`, and asserts: (a) the response status is `502` or `503` (not 500), (b) the body contains a human-readable error, (c) no `X-Citations` header is set, (d) the `queries.views` logger captures an ERROR line. Mirror the test for `AskPageView`.

## High — No integration test for "empty ChromaDB collection" query path
**File:** `policyiq/queries/services/retriever.py:60-87`, `policyiq/queries/services/generator.py:130-148`
**Issue:** The `retriever` returns `[]` when ChromaDB has no matches, and `build_prompt` returns `None` when no chunk clears the threshold. The view's "no relevant information" branch is tested at the unit level (`test_views.py:68-78, 168-178`) but there is no test for the case where the library is *populated* yet a specific query returns no chunks above threshold (e.g., a vague "hello" question). That is a high-risk path: the user types something the LLM shouldn't be able to answer, and the app should say so clearly. The current path returns a 200 with `"No relevant information found"`, but the log line and the citation header set (or not set) are not asserted.
**Fix:** Add a test that mocks `retrieve_chunks` to return `[]`, drives a real `QueryAPIView.post` request, and asserts: (a) status 200, (b) JSON body has the `answer` field with the "no relevant information" string, (c) no `X-Citations` header (or it is `[]`), (d) `generate_response` was never called. Also add a test for chunks-below-threshold (e.g., a chunk with `similarity_score=0.3` should produce the same "no relevant information" response).

---

## Medium — `Chunk` is stored in both PostgreSQL and ChromaDB — content redundancy
**File:** `policyiq/documents/models.py:25-37`, `policyiq/documents/services/pipeline.py:58-68`, `policyiq/documents/services/indexer.py:30-80`
**Issue:** Every chunk's `text` is written to two places: the `Chunk` table in PostgreSQL (`bulk_create` in pipeline.py:58-68) and the `documents` field of a ChromaDB record (`indexer.py:46, 60`). The `Chunk` model is never *read* anywhere — `retriever.py:67` reads chunk text from ChromaDB's response, not from PostgreSQL. The `text` column on `Chunk` is therefore pure storage duplication: every ingest round-trips a full copy of the document to PG. The `admin.py` only displays `page_number` and `token_offset` (`admin.py:14`), not `text`, so even Django admin doesn't benefit from the PG copy.
**Fix:** Pick one. The natural choice is "chunks live in ChromaDB only" — drop the `text` column from `Chunk`, or drop the entire `Chunk` model. That removes the `bulk_create` call from the pipeline, halves the write cost on ingest, and lets you remove `Chunk.objects.filter(document=document).delete()` from the reindex path (ChromaDB delete already covers it). If you want to keep `Chunk` for relational queries (e.g., "show me all chunks from page 12 of doc X" in admin), drop the `text` field and let `Chunk` carry only the `(document, page_number, token_offset)` pointer — the actual text is fetched from ChromaDB on demand. Document the decision either way in `CLAUDE.md`.

## Medium — `pipeline.py` has explicit code in the view layer that should live in the pipeline
**File:** `policyiq/documents/views.py:48-124` (`_save_upload_and_ingest`)
**Issue:** The view's `_save_upload_and_ingest` does five things: validate the upload, save to temp storage, create a `Document` row, call `ingest_document`, and clean up on failure. The temp-file lifecycle (save → open → chunk-write → delete-on-error) and the `Document.objects.create` are view-layer concerns, but they are tangled with the pipeline's `bulk_create` and `index_document` call. This makes the pipeline non-reusable from outside the view — e.g., a future "bulk import from a directory" management command would have to re-implement all the temp-file and rollback logic. (Per the task spec: "Is the pipeline callable as a unit from outside the view?" — the answer is technically yes via `ingest_document(document)`, but the surrounding cleanup is not.)
**Fix:** Move the *full* lifecycle into a service: `documents/services/pipeline.py::ingest_uploaded_pdf(upload_file, username=None) -> Document` that owns the temp path, `Document` creation, ingestion, and rollback. The view becomes a 5-line adapter that calls it and serializes the result. Keep `ingest_document(document, file_path=None)` as the lower-level primitive that the management command would call. The current `_save_upload_and_ingest` is also duplicated between `UploadPageView.post` and `DocumentUploadAPIView.post` (both call it), so the extraction kills two birds.

## Medium — `_validate_pdf` is duplicated across three upload paths but with subtle drift
**File:** `policyiq/documents/views.py:29-45` (definition), called in `views.py:68, 161, 277`
**Issue:** `_validate_pdf` is a module-level function called from `UploadPageView.post`, `DocumentUploadAPIView.post`, and *twice* in `_save_upload_and_ingest` (once for the "validation should be caught by the caller" path at line 68, once in the views at 161/277). The double call is intentional (defense in depth) but it is easy to drift. The error strings are constructed inline and not centralized. The function does not check file size (the throttle layer is the only size gate, via DRF's `DATA_UPLOAD_MAX_MEMORY_SIZE` / per-view limits).
**Fix:** Either (a) drop the in-`_save_upload_and_ingest` call and trust the view's validation, or (b) document explicitly that the inner call is a "second-line" check. Add a size check (e.g., 50 MB max PDF) to `_validate_pdf` so a 500 MB file doesn't get streamed to disk and then fail at the embedder.

## Medium — `Chunk.objects.filter(document=document).delete()` in reindex is unnecessary if `delete_document` already covers it
**File:** `policyiq/documents/views.py:252`
**Issue:** `StaffDocumentReindexView.post` calls `Chunk.objects.filter(document=document).delete()` *and* `delete_document(str(document.id))`. The ChromaDB delete is scoped by `document_id` metadata and is sufficient to remove all chunks. The PG `Chunk` delete is redundant *unless* the `Chunk.text` column is intentionally preserved as a relational backup (see the previous finding). If the previous finding is resolved by dropping the redundant PG storage, this line can be removed entirely.
**Fix:** Resolve the redundancy first, then drop this line as a follow-up. The line is harmless today but obscures the source of truth.

## Medium — `StageTimer` (`timing.py`) is defined but unused
**File:** `policyiq/queries/services/timing.py:18-40`
**Issue:** `stage_timer` is exported, tested (`test_timing.py`), and never called. Every stage in `pipeline.py`, `embedder.py`, `chunker.py`, `indexer.py`, `generator.py`, and `retriever.py` measures its own duration with inline `t0 = time.monotonic()` blocks and writes a hand-rolled log line. The helper would consolidate ~10 ad-hoc timing blocks into one idiom and remove the `logger_` parameter that the docstring admits is "reserved for future use" (i.e., the API is larger than the implementation justifies).
**Fix:** Either adopt `stage_timer` everywhere (replace the `t0 = ...; ...; logger.info("X in %.2fs", ...)` pattern with `with stage_timer("X") as t: ...; logger.info("X in %.2fs", t["elapsed_s"])`), or delete `timing.py` and `test_timing.py` until it has a real consumer. Today it is dead code that implies a contract the codebase doesn't honor.

## Medium — `generator.py` exposes `_generate_ollama` / `_generate_anthropic` as importable, tests import the private name
**File:** `policyiq/queries/services/generator.py:24, 56`, `policyiq/queries/tests/test_services.py:8, 233, 250, 261`
**Issue:** The leading underscore signals "private" but `queries.tests.test_services` imports `_generate_anthropic` directly. This is a smell — either the function is meant to be tested in isolation (so drop the underscore) or the test should go through `generate_response` with a `LLM_BACKEND=anthropic` setting. The test for the ollama path already uses `generate_response` and only patches `requests.post`; the anthropic test bypasses the public dispatch.
**Fix:** Drop the underscores (or move to a `backends` submodule). At minimum, route the anthropic test through `generate_response` with `LLM_BACKEND=anthropic` and a mocked `anthropic.Anthropic` — the dispatch path then gets covered too.

## Medium — Streaming response test only verifies the fully-buffered body, not incremental delivery
**File:** `policyiq/queries/tests/test_views.py:47-63` (`test_post_streams_answer_when_chunks_found`)
**Issue:** The test does `b"".join(response.streaming_content).decode("utf-8")` and asserts the concatenated string. This is equivalent to asserting the final body — it doesn't verify that the response is *streamed* (e.g., that the first chunk is delivered before the generator is exhausted). For a `StreamingHttpResponse` consumed by HTMX, what matters is that tokens arrive incrementally so the UI updates. The current test would pass even if the response were buffered.
**Fix:** Use `response.streaming_content` as a generator and assert that it yields multiple chunks (e.g., by calling `next()` on it before `b"".join`). Or use Django's test client's `streaming_content` iterator and check that the first chunk arrives before the last call to `generate_response` is made (use a `mock_generate_response` that records call order via a side effect). At minimum, add a test that drives the response with `RequestFactory` and reads the iterator element-by-element to confirm streaming semantics.

## Medium — `extract_pages` does not import and use the project's domain exceptions
**File:** `policyiq/documents/services/extractor.py:11-46`
**Issue:** `extract_pages` raises `FileNotFoundError` and `ValueError` directly. The rest of the pipeline uses `ExtractionError` (defined in `documents/exceptions.py:8`) which subclasses `DocumentError`, and the pipeline's `pipeline.py:109-114` stage-mapping only knows about `ExtractionError`. A `ValueError` from the extractor (e.g., corrupted PDF) is not classified as a pipeline "extract" failure, so the log line on ingestion failure will show `stage=unknown` instead of `stage=extract`. The unit test `test_extract_pages_raises_value_error_for_corrupted_pdf` even codifies the wrong exception type.
**Fix:** Wrap the `ValueError` and `FileNotFoundError` re-raises in `ExtractionError` (or raise `ExtractionError` directly from the extractor). Update the unit test. Add a pipeline test that drives a `ValueError` and asserts the log line says `stage=extract`.

## Medium — `embedder.py` does not raise on a 2xx response with a missing or wrong-shape `embeddings` list consistently
**File:** `policyiq/documents/services/embedder.py:67-72, 104-107`
**Issue:** `_embed_batch_with_retry` raises `ValueError` if `embeddings` is not a list or has the wrong length — good. `_embed_single_with_retry` raises `ValueError` if `embeddings` is not a list or is empty — also good. But neither path validates the *individual vector shapes* (a vector could be a list of strings, or a list of one float, or any other nonsense) and `_normalize` would raise `TypeError` on a non-numeric entry. A bad model name on the Ollama side (e.g. `nomic-embed-text-v2` not pulled) returns a 404-like body that the code does not classify — `raise_for_status` only fires on 4xx/5xx HTTP codes, but Ollama returns 200 with `{"error": "model not found"}` for that case, and the current code will treat it as a successful empty list.
**Fix:** Add a top-level "is this an Ollama error envelope" check: if `data` has an `error` key, raise `EmbeddingError` (or a new `OllamaError`) immediately. Validate each vector's elements are floats. Make the malformed-response branch more descriptive in its log line so operators can tell the difference between "Ollama down" and "wrong model pulled".

## Medium — Test coverage gap: the `DocumentDeleteView` (non-staff) path has no tests
**File:** `policyiq/documents/views.py:200-211` (the public, non-staff view), `policyiq/documents/tests/test_views.py`
**Issue:** `test_views.py` has `StaffDocumentDeleteViewTests` (line 231) but no test for `DocumentDeleteView`. The two are not the same — `DocumentDeleteView` has no `@method_decorator(staff_member_required)` and is reached at `path("documents/<uuid:pk>/delete/")` in `urls.py:27`. It is also wired up in `templates/documents/history.html:31` as `hx-delete="{% url 'document-delete' %}"`. So a regular authenticated user (or an unauthenticated one, since there is no permission check) can delete any document. That is probably a bug, not a feature.
**Fix:** Decide what the intended permission model is (any logged-in user? document owner only? staff only?). Add the appropriate `LoginRequiredMixin` / `Permission` class, then add tests. The current state — public DELETE endpoint with no auth — is the kind of thing an audit will catch.

## Medium — Test coverage gap: the `StaffDocumentReindexView` reindex failure path is not tested
**File:** `policyiq/documents/tests/test_views.py:260-296`
**Issue:** The test `test_staff_reindex_delegates_to_ingest_document` only covers the happy path. If `ingest_document` raises, the view returns `HttpResponse(status=200)` because the exception propagates unhandled — Django's default 500 page is shown. The previous "high"-priority finding covers the data-loss aspect; this finding covers the test gap.
**Fix:** Add a test that mocks `ingest_document` to raise `ExtractionError` and asserts the response is `500` (or, if you fix the view to catch and return `500` explicitly, assert that). Add a test that asserts `Chunk.objects.filter(document=document).delete()` ran *before* `ingest_document` was called (i.e., old chunks were purged even if the new run fails — current code does this correctly, but no test pins it).

## Medium — Test coverage gap: the `HistoryPageView` and `HomePageView` have partial coverage
**File:** `policyiq/documents/tests/test_views.py:630-685`
**Issue:** `HomePageView` has 3 tests covering the happy path. `HistoryPageView` (`policyiq/documents/views.py:191-197`) has *zero* tests. The view does a `Document.objects.order_by("-uploaded_at")` and renders the template; a regression that breaks the ordering or template context would not be caught.
**Fix:** Add `HistoryPageViewTests` with at least: empty-DB renders 200 with no document rows; 2-doc DB renders both in reverse-chronological order; an uploaded document with a special-character name (e.g. `Aetna&2026.pdf`) renders without HTML-injection. (The third test catches the missing `escape` on `{{ document.name }}` in `templates/documents/history.html`.)

## Medium — Test coverage gap: the streaming `Ollama` generator's mid-stream connection drop is not tested
**File:** `policyiq/queries/services/generator.py:24-49`
**Issue:** `_generate_ollama` opens a streaming response and iterates `response.iter_lines()`. If the connection drops mid-stream (Ollama killed, network blip), the `requests` library raises `ChunkedEncodingError` or `ConnectionError`, which subclasses `RequestException` — so the `except (requests.RequestException, json.JSONDecodeError)` catches it. But the catch path doesn't yield a final token; it raises `GenerationError`. The current tests only cover "Ollama never responds" and "Ollama responds cleanly" — not "Ollama streams 5 tokens then disconnects".
**Fix:** Add a test that mocks `requests.post` to return a response whose `iter_lines()` yields 3 lines and then raises `requests.exceptions.ChunkedEncodingError`. Assert that the generator raises `GenerationError` (or, if you decide to be more graceful, yields an error sentinel and stops).

## Medium — Test coverage gap: the `health.py` helpers' failure paths are marked `# pragma: no cover`
**File:** `policyiq/queries/services/health.py:24, 34, 46`
**Issue:** The `except Exception` branches in `check_postgresql`, `check_chromadb`, `check_ollama` all have `# pragma: no cover - exercised via tests`. That comment is partly true (`test_health.py` covers them), but the comment signals uncertainty and there is no CI guard to confirm it. If a refactor drops the `except` line, coverage won't catch it.
**Fix:** Drop the `# pragma: no cover` comments — `test_health.py` covers them already (`test_health.py:19-26, 64-71, 73-82`).

## Medium — Test coverage gap: `DocumentUploadAPIView` and `UploadPageView` partial-upload behavior is not tested
**File:** `policyiq/documents/views.py:148-188, 266-310`
**Issue:** Both views iterate `request.FILES.getlist("file")` and accumulate per-file results. The status-code logic (`has_success` / `has_validation_error` / 500) is non-trivial:
- All files succeed → 201
- Some succeed, some fail validation → 201 (any success wins)
- All files fail validation → 400
- All files fail at the pipeline → 500

No test exercises the mixed-success case (one PDF OK, one PDF rejected). The "all pipeline failures" case is also untested — it falls through to `status.HTTP_500_INTERNAL_SERVER_ERROR` but the loop appends each failure as a dict with `success: False`, so the response shape is `{"results": [{...}, {...}]}` rather than `{"error": "..."}`. The serializer validation (`UploadResultSerializer.is_valid`) could reject the failure dicts if the schema is wrong.
**Fix:** Add tests for: 2-file upload with 1 success and 1 pipeline failure (assert 201 and a results list of 2), 2-file upload with 1 success and 1 validation failure (assert 201), 1-file upload that fails the pipeline (assert 500), 1-file upload that fails validation (assert 400). Also assert that the `UploadResultSerializer` accepts the failure-shape dict that the loop produces (no `document_id` field).

---

## Low — `MEDIA_ROOT` test override at `tempfile.gettempdir()` is shared, not isolated
**File:** `policyiq/documents/tests/test_views.py:32, 67, 489, 525, 560, 597`, `policyiq/tests/integration/test_integration.py:53-54`
**Issue:** Several tests use `@override_settings(MEDIA_ROOT=tempfile.gettempdir())`. Because Django's storage layer is a singleton, parallel test runs (or even sequential runs with leftover files) can collide on the same temp directory. The integration test uses a subdirectory `policyiq_test_media` which is safer.
**Fix:** Use `tempfile.mkdtemp()` per test (in `setUp`/`tearDown`) and clean up. Or just use `tempfile.mkdtemp()` in the override.

## Low — `_STAGE_BY_EXCEPTION_NAME` in pipeline uses a string-name lookup, fragile to renames
**File:** `policyiq/documents/services/pipeline.py:97-114`
**Issue:** The stage label is derived from `type(exc).__name__` and looked up in a dict keyed by the exception class name string. If `ExtractionError` is renamed, the log line silently says `stage=unknown` (the default). If a new exception class is added, the mapping has to be updated by hand. The pipeline already imports the exception classes — could use `isinstance` instead.
**Fix:** Replace the dict with an `isinstance` ladder: `if isinstance(exc, ExtractionError): stage = "extract"` etc. The current test `test_pipeline_logs_failure_at_extractor_stage` would still pass.

## Low — `OllamaClient` cache key collisions across settings overrides
**File:** `policyiq/documents/services/indexer.py:19-22` (`@functools.lru_cache(maxsize=1)`)
**Issue:** `get_chroma_client` is cached on the `PersistentClient` instance, which is bound to a specific `path` at construction time. If a test uses `override_settings(CHROMA_PERSIST_DIR=...)` after the first call has populated the cache, the override is silently ignored. The unit tests dodge this by calling `get_chroma_client.cache_clear()` in `setUp` (`test_services.py:211, 308`).
**Fix:** Either (a) include the path in the cache key by making the function take a parameter, or (b) add a `cache_clear()` call to `override_settings` listeners. Today the silent ignore is hidden behind the manual `setUp` calls and is easy to forget.

## Low — Logging in views duplicates the work the services already log
**File:** `policyiq/documents/views.py:61-66, 74, 89, 105-110, 117-122` and `policyiq/queries/views.py:50, 56-58, 69-74, 98, 104-105, 120-125`
**Issue:** The views log "Received upload", "Validated PDF magic bytes", "Wrote X to Y", "Dispatched ingestion for X (document_id=Y) in T.TTs", then the pipeline logs "Starting ingestion", "Extracted", "Created chunks", "Embedded chunks", "Indexed", "Ingestion complete". For one upload, you get ~10 INFO log lines from two loggers. Operators reading the log see "Did the upload work?" and have to scan 5+ lines to confirm. The view-level lines mostly echo what the pipeline already says.
**Fix:** Pick one place to log the "user-visible" receipt. Either: (a) the view logs only "Received upload" and "Ingestion complete (id=X, pages=N, chunks=M, duration=Ts)" — the services log the rest, but the view wraps the call with its own timer; or (b) the view doesn't log at all and the pipeline's "Ingestion complete" line is the receipt. Same applies to the query path: "Query received" + "Streamed answer" in the view duplicate "Retrieving up to N chunks" + "Retrieved N chunks" + "Streaming from X" + "Generated N tokens" in the services.

## Low — `MAX_QUESTION_LOG_CHARS` is used in `views.py` but defined in `retriever.py`
**File:** `policyiq/queries/views.py:48, 96`, `policyiq/queries/services/retriever.py:12`
**Issue:** `MAX_QUESTION_LOG_CHARS` is a retriever-internal constant (it caps the log line in `retriever.py:45`), but the views import and reuse it. The import is fine, but the constant is misnamed — it caps the log line in the *view's* receipt too, even though the retriever is the one that "owns" it.
**Fix:** Move `MAX_QUESTION_LOG_CHARS` to a queries-level constants module (e.g., `queries/constants.py`) and import it from both `retriever.py` and `views.py`. The current import works, but the cross-module dependency on an "internal" constant is a smell.

## Low — `document.file.path` assumes local filesystem storage
**File:** `policyiq/documents/services/pipeline.py:32`, `policyiq/documents/views.py:88`
**Issue:** `document.file.path` and `default_storage.path(temp_path)` only work with `FileSystemStorage`. If the project ever moves to S3 / GCS via `django-storages`, both lines raise `NotImplementedError`. The temp-file write loop (`default_storage.open(temp_path, "wb")`) and the `default_storage.exists` / `default_storage.delete` calls would also break.
**Fix:** Today this is "YAGNI" since `settings.py:96` hardcodes `MEDIA_ROOT = BASE_DIR / "media"`. Add a comment near `MEDIA_ROOT` and at the call sites stating the local-FS assumption, or gate the call sites on `isinstance(default_storage, FileSystemStorage)`.

## Low — `DocumentUploadAPIView.post` and `UploadPageView.post` have nearly identical logic
**File:** `policyiq/documents/views.py:148-188` vs `policyiq/documents/views.py:266-310`
**Issue:** Both POSTs do the same per-file loop, accumulate the same `results` list, and compute the same status code. The only differences are (a) input source, (b) error envelope shape (template vs JSON), and (c) serializer validation. The duplication is exactly the case the `enterplanmode` would call out — ~40 lines of mirrored code.
**Fix:** Extract `_process_uploads(uploads, request) -> tuple[list[dict], int]` that returns the results list and the status code. Both views call it and then render. Combined with the earlier "extract the upload pipeline into a service" finding, the views shrink to ~10 lines each.

## Low — `Ollama` timeout constants are inconsistent (30 s vs 60 s)
**File:** `policyiq/documents/services/embedder.py:64, 101`
**Issue:** `_embed_batch_with_retry` uses `timeout=60` and `_embed_single_with_retry` uses `timeout=30`. The 30 s choice for single-query is reasonable (the user is waiting), but a 32-chunk batch with a slow Ollama instance could legitimately take more than 60 s — and the retry on timeout is a full 3 × 60 = 180 s of waiting, which is the difference between a snappy UI and a 502. The timeouts are not configurable.
**Fix:** Promote `EMBEDDING_BATCH_TIMEOUT`, `EMBEDDING_QUERY_TIMEOUT`, `GENERATION_TIMEOUT` to settings. Use the same value (e.g., 60 s) for both batch and single-shot, and document the upper bound.

## Low — `streaming_content` test approach in `test_views_pytest.py` duplicates the Django TestCase version
**File:** `policyiq/queries/tests/test_views_pytest.py:32-157`
**Issue:** The pytest-style tests in this file are almost identical to the Django TestCase tests in `test_views.py` (same mocks, same assertions, same inputs). The only difference is `pytest.mark.django_db` and pytest fixture style. Per the project guideline "Django: split tests into `test_models.py`, `test_views.py`, `test_serializers.py`", maintaining two parallel test files for the same view is a maintenance burden.
**Fix:** Pick one. The pytest-style file's docstring (`test_views_pytest.py:1-14`) says it exists to "demonstrate coexistence" — that's a one-time experiment, not an ongoing need. Either delete `test_views_pytest.py` (the `conftest.py` fixtures are still useful for any future pytest tests) or delete the equivalent tests in `test_views.py` and commit to pytest.

## Low — `CHANGELOG.md` line 99 mentions `lru_cache` and one-time init
**File:** `docs/CHANGELOG.md:99`
**Issue:** Not a code finding, but a doc/code mismatch: the changelog says "`get_collection()` now reuses the singleton client instead of creating a new one on every call". The current code is correct, but if a future refactor moves the ChromaDB client to a Django app-config-level singleton (a more conventional Django pattern), the helper is no longer needed and the doc claim becomes stale.
**Fix:** Consider whether the lru_cache trick should stay or be replaced with a module-level lazy singleton (`_client = None; def get_client(): global _client; if _client is None: _client = ...; return _client`). The current pattern works, but the "magic" of lru_cache on a chromadb client is unusual.

## Low — `extract_pages` always reads the full PDF into memory via `page.get_text()`
**File:** `policyiq/documents/services/extractor.py:26-30`
**Issue:** For very large PDFs (hundreds of pages), holding every page's raw text in memory simultaneously is wasteful. PyMuPDF supports `get_text()` streaming, and the chunker later concatenates `all_tokens` across all pages (`chunker.py:20-28`), so the pipeline is already memory-bound on `len(all_tokens)`.
**Fix:** Defer — this is a perf optimization, not a correctness issue. Flag it for the next round of perf work.

## Low — `clean_pages` repeats the full pass twice (one to count, one to filter)
**File:** `policyiq/documents/services/extractor.py:52-82`
**Issue:** `clean_pages` makes two passes over the page list: one to build `line_counts` (which scans every line of every page) and one to filter (which scans again to apply the rules). For a 500-page document, this is 1000 line iterations vs. 500. The counter logic also lives in a separate function so it can't be fused with the filter pass.
**Fix:** Defer — current behavior is correct and clear. A single-pass version would need a "first N occurrences" rule to avoid dropping content from the first 3 pages. Not worth the complexity until profiling says so.

## Low — `health.check_ollama` hardcodes `/api/tags` instead of using a configurable health endpoint
**File:** `policyiq/queries/services/health.py:41-48`
**Issue:** Hardcoded `/api/tags` URL. The shared `ollama_client.py` (proposed in a high-priority finding) could expose a `health_check()` method that uses the same connection setup.
**Fix:** Once the shared client exists, replace `requests.get(f"{OLLAMA_BASE_URL}/api/tags", ...)` with `ollama_client.ping()`.

## Low — `_DynamicRateMixin` is duplicated verbatim across `documents/throttles.py` and `queries/throttles.py`
**File:** `policyiq/documents/throttles.py:16-33` and `policyiq/queries/throttles.py:16-33`
**Issue:** The same `_DynamicRateMixin` class is defined in both app throttles modules. The four throttle classes themselves (Upload* and Query*) are also near-identical. There is no difference in behavior, only in the `scope` attribute.
**Fix:** Extract a `policyiq/throttles.py` (or `core/throttles.py`) module with the mixin and the four throttle subclasses. Each app re-exports the ones it needs.

## Low — `documents/views.py:200-211` `DocumentDeleteView` and `views.py:225-237` `StaffDocumentDeleteView` are 95% identical
**File:** `policyiq/documents/views.py:200-211` vs `policyiq/documents/views.py:225-237`
**Issue:** The two views have the same body; the only difference is the `@method_decorator(staff_member_required, name="dispatch")` on the staff version. Combined with the missing `DocumentDeleteView` tests, this is two views to maintain for no benefit.
**Fix:** Either drop `DocumentDeleteView` and require staff for all deletes, or fold both into a single view whose auth check is configurable. The test gap (medium finding above) suggests the public path was likely added by accident.

---

## Summary table

| Tier | Count | Theme |
| --- | --- | --- |
| High | 8 | Pipeline rollback, view duplication, hardcoded config, error surfacing |
| Medium | 13 | Chunk redundancy, dead code, exception classification, test coverage |
| Low | 12 | Log noise, cross-app duplication, deferred perf, doc/code alignment |

The single highest-leverage change is extracting a shared `ollama_client.py` and promoting the hardcoded constants to `settings.py` (touches 4 modules, removes ~80 lines of duplication, makes deployment-time config changes possible). The second is collapsing the two upload views and the two query views onto a shared service function.
