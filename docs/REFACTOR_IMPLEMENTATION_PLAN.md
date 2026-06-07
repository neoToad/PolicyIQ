# PolicyIQ Refactor Implementation Plan

A phased, test-driven implementation plan to address every finding in [`docs/REFACTOR_AUDIT.md`](./REFACTOR_AUDIT.md) (8 High, 13 Medium, 12 Low). The plan is organized into **six phases** ordered by dependency, so each phase leaves the codebase green and unblocks the next.

> **Workflow rule (from `AGENTS.md`):** Every feature below follows TDD — failing tests first, confirm the failure is for the right reason, then implement the minimum to make them pass. No commit message is generated while tests are red. Tests are split per Django app convention into `test_models.py`, `test_views.py`, `test_serializers.py`, plus `test_services.py` / `test_pipeline.py` where the unit under test is a service.

> **Conventions:** New settings live in `policyiq/policyiq/settings.py`. New shared modules live in `policyiq/` (project root) when consumed by multiple apps, and in `policyiq/<app>/services/` when owned by a single app. Each phase ends with a `chore(refactor):` commit and a `docs(logging):` / `docs:` entry if behavior changed.

---

## Phase 0 — Foundation: shared settings + shared Ollama client (touch everything else)

**Why first:** The High finding "Hardcoded model names, URLs, and tunables" (audit H3) and the High finding "Duplicated Ollama HTTP call pattern" (audit H4) both touch 4–5 modules. Several later phases (H1, H5, H6, M1, M13, L9) consume the new client or the new settings, so building this first prevents rework.

### 0.1 Centralize settings (audit H3, L9, L13)

**Files touched:** `policyiq/policyiq/settings.py`, every service module, every view module, every test that referenced the old constants.

**New settings (with env-var defaults):**
- `OLLAMA_BASE_URL` = `os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")` (the existing setting — keep name, but actually use it).
- `OLLAMA_EMBED_URL` and `OLLAMA_GENERATE_URL` derived from `OLLAMA_BASE_URL` via a small helper in `policyiq/services/__init__.py` (or a top-level `policyiq/ollama.py` once it exists in 0.2).
- `OLLAMA_EMBED_MODEL` (default `"nomic-embed-text"`).
- `OLLAMA_GENERATE_MODEL` (default `"llama3.2"`).
- `ANTHROPIC_MODEL` (default `"claude-sonnet-4-20250514"`).
- `ANTHROPIC_MAX_TOKENS` (default `1024`).
- `EMBEDDING_RETRY_ATTEMPTS` (default `3`).
- `EMBEDDING_RETRY_DELAY` (default `1`).
- `EMBEDDING_BATCH_SIZE` (default `32`).
- `EMBEDDING_BATCH_TIMEOUT` (default `60`).
- `EMBEDDING_QUERY_TIMEOUT` (default `30`).
- `GENERATION_TIMEOUT` (default `60`).
- `CHUNK_SIZE` (default `500`).
- `CHUNK_OVERLAP` (default `50`).
- `RETRIEVAL_TOP_K` (default `5`).
- `SIMILARITY_THRESHOLD` (default `0.5`).
- `SIMILARITY_BAR_HIGH` (default `0.75`) — for the JS bar boundary in `templates/queries/ask.html:69`.
- `PDF_MAX_BYTES` (default `50 * 1024 * 1024`).
- `MEDIA_ROOT_ASSUMES_LOCAL_FS` comment near `MEDIA_ROOT` (audit L10).

**TDD steps:**
1. **Failing test:** `policyiq/tests/test_settings.py::test_required_settings_present` reads `getattr(settings, "OLLAMA_EMBED_MODEL", None)` and asserts the value. Add a new test that imports a helper `policyiq/services/llm_config.py::get_ollama_embed_url()` and asserts the URL is built from `OLLAMA_BASE_URL`. (Both fail because the helper and the settings don't exist yet.)
2. **Implement:** Add the settings entries, write the helper, export it.
3. **Refactor:** Replace every literal in `embedder.py`, `generator.py`, `chunker.py`, `retriever.py`, `views.py`, `health.py` with a `settings.X` read (or a helper) — one module at a time, keeping tests green between modules.
4. **Surface to template:** Add a context processor in `policyiq/documents/context_processors.py` (or `policyiq/policyiq/context_processors.py`) that injects `SIMILARITY_THRESHOLD` and `SIMILARITY_BAR_HIGH`. Update `templates/queries/ask.html:69` to read them.
5. **Verify:** `pytest -x policyiq` and a manual smoke for the JS bar.

**Commit cadence:** one `chore(settings):` for the new entries, then one `refactor(embedder): use settings.X` per module, then one `feat(templates): threshold from context`.

### 0.2 Build the shared `ollama_client.py` (audit H4, L13, L20)

**New file:** `policyiq/policyiq/ollama.py` (or `policyiq/services/ollama_client.py` if you prefer an app-shaped tree at the project root; pick one and stick with it — recommended: `policyiq/policyiq/ollama.py` because it's project-wide infrastructure, not a domain service).

**Public API:**
- `class OllamaError(Exception)` — base for `EmbeddingError` / `GenerationError` aliases.
- `post_json(path: str, payload: dict, *, timeout: float) -> dict` — single POST with the shared retry loop, returning parsed JSON or raising `OllamaError`. Uses `EMBEDDING_RETRY_ATTEMPTS` / `EMBEDDING_RETRY_DELAY` from settings.
- `post_stream(path: str, payload: dict, *, timeout: float) -> Iterator[dict]` — streaming variant for `/api/generate` that yields decoded JSON lines, raising `OllamaError` on transport failure.
- `embed_texts(model: str, texts: list[str]) -> list[list[float]]` — thin wrapper over `post_json("/api/embed", ...)`.
- `embed_query(model: str, text: str) -> list[float]` — thin wrapper over `post_json("/api/embed", ...)`.
- `generate(model: str, prompt: str, *, stream: bool) -> Iterator[str] | str` — thin wrapper that picks `post_stream` or `post_json("/api/generate", ...)` based on `stream`.
- `ping() -> bool` — uses `GET /api/tags` (audit L20).
- `is_error_envelope(data: dict) -> bool` — detects `{"error": "..."}` from Ollama 200 responses (audit M8).
- `validate_embedding_vector(vec: list) -> list[float]` — checks each element is a number (audit M8).

**TDD steps:**
1. **Failing tests** in `policyiq/tests/test_ollama_client.py`:
   - `test_post_json_returns_parsed_dict` — patches `requests.post` to return `Mock(json=lambda: {"ok": True}, raise_for_status=lambda: None)`.
   - `test_post_json_retries_on_request_exception` — patches `requests.post` to raise twice then succeed; asserts 3 calls.
   - `test_post_json_raises_ollama_error_after_max_attempts` — patches to always raise; asserts `OllamaError`.
   - `test_post_json_raises_on_http_error_status` — patches to return 500 with `raise_for_status` that raises.
   - `test_post_json_raises_on_error_envelope` — patches to return 200 with `{"error": "model not found"}`; asserts `OllamaError` and message contains `"model not found"`.
   - `test_post_stream_yields_decoded_lines` — patches `iter_lines` to yield 3 JSON lines; asserts the iterator yields 3 dicts.
   - `test_post_stream_raises_on_midstream_disconnect` — patches `iter_lines` to yield 2 lines then raise `ChunkedEncodingError`; asserts `OllamaError` (this is also the H7 / M10 test in a different home).
   - `test_validate_embedding_vector_rejects_strings` — asserts `TypeError` (or `OllamaError`) on a `["a", "b"]` input.
   - `test_ping_returns_true_on_200` and `test_ping_returns_false_on_connection_error`.
2. **Implement** the client. Keep it small and dependency-free.
3. **Migrate** `embedder.py` and `generator.py` to call into the client. Delete the local `_embed_batch_with_retry` / `_embed_single_with_retry` / `_generate_ollama` HTTP code. The only thing left in `embedder.py` should be: shape normalization, batching, and the `embed_chunks` / `embed_query` public entry points.
4. **Verify** all existing tests in `policyiq/documents/tests/test_services.py` and `policyiq/queries/tests/test_services.py` / `test_generator.py` still pass with no changes (or with minimal mock-patch updates if the mock targets changed).

**Commit cadence:** `feat(infra): add ollama_client with retry and error-envelope detection`, then `refactor(embedder): use shared ollama_client`, then `refactor(generator): use shared ollama_client`, then `refactor(health): use shared ollama_client.ping`.

### 0.3 Verify Phase 0

Run `pytest -x` and a manual smoke (upload a PDF, run a query, hit `/healthz/`). If green, tag the commit and move on.

---

## Phase 1 — Pipeline rollback safety (audit H1)

**Why second:** This is the highest-stakes correctness issue. It depends on the Ollama client (for clearer error types) and on settings (for the chunk/batch counts that drive rollback). It also unlocks the simpler reindex test in M11.

### 1.1 Make the pipeline atomic and ordered (audit H1)

**File:** `policyiq/documents/services/pipeline.py:36-106` and `policyiq/documents/views.py:244-257` (reindex).

**TDD steps:**
1. **Failing tests** in `policyiq/documents/tests/test_pipeline.py` (new section `AtomicityTests`):
   - `test_pipeline_rolls_back_chunks_on_indexer_failure` — patches `index_document` to raise `IndexingError`, drives a real `ingest_document(document)`, asserts `Chunk.objects.filter(document=document).count() == 0` and `Document.page_count is None`.
   - `test_pipeline_rolls_back_indexer_writes_on_bulk_create_failure` — patches `Chunk.objects.bulk_create` to raise `IntegrityError`, asserts no ChromaDB records exist (use a mock `get_chroma_client` that tracks `.delete` calls).
   - `test_pipeline_uses_atomic_block` — uses `assertNumQueries` with `atomic=True` flag, or a simpler `captureOnCommitCallbacks`-style assertion: write a test that confirms PG state and ChromaDB state are committed together or not at all.
   - `test_reindex_does_not_leave_orphan_chunks_on_failure` — runs `StaffDocumentReindexView` with `ingest_document` patched to raise, asserts `Chunk.objects.filter(document=document).count() == 0` after the call (because the pre-delete already happened AND the new run rolled back).
   - `test_pipeline_orders_bulk_create_after_indexer` — patches `index_document` to raise before any `bulk_create` is attempted; asserts no PG writes happened.
2. **Implement:** Wrap the entire `ingest_document` body in `transaction.atomic()`. Run `index_document` first; on success, run `bulk_create`. On any failure inside the `with` block, the transaction rolls back the PG side and we also explicitly call a `delete_document(document_id)` (or a per-chunk-ID rollback if you went that route) to compensate the vector store. The reindex path inherits the same safety because it just calls `ingest_document`.
3. **Verify** all existing pipeline tests in `test_pipeline.py` still pass.

**Commit:** `fix(pipeline): atomic write order with indexer-first, vector compensation on failure`.

### 1.2 Add a swept "vector orphan" marker (audit H2, partial)

Once H1 is fixed, the orphaned-chunk problem is mostly solved. The "vector orphan" marker from the H2 finding can be deferred to a follow-up sweeper job — log a warning with `document_id` and `chunk_count` whenever `index_document` fails after `bulk_create` succeeds, so an ops job can sweep. No new table needed yet.

---

## Phase 2 — Delete-path safety (audit H2)

**Why third:** Similar atomicity problem on the delete path. Now that the pipeline is atomic, the same pattern is easy to apply here. Also tests for the public `DocumentDeleteView` are a precondition for fixing the permission gap (M7).

### 2.1 Extract `delete_document_with_chunks` service (audit H2)

**New file:** `policyiq/documents/services/deletion.py`.

**TDD steps:**
1. **Failing tests** in `policyiq/documents/tests/test_services.py` (new section `DeletionServiceTests`):
   - `test_delete_document_with_chunks_removes_pg_and_chromadb` — happy path, asserts `Chunk.objects.count() == 0` and `delete_document` was called.
   - `test_delete_rolls_back_pg_on_chromadb_failure` — patches `delete_document` to raise, asserts `Document` row still exists.
   - `test_delete_rolls_back_chromadb_on_pg_failure` — harder to simulate cleanly without `transaction.atomic` mocking; instead, assert that the function is wrapped in `transaction.atomic` and that the PG delete happens *after* the ChromaDB delete (use a mock that tracks call order).
   - `test_delete_creates_vector_orphan_marker_on_chromadb_failure` — assert a logger WARNING line is emitted.
2. **Implement** the service: `transaction.atomic()` block, `delete_document(str(document.id))` first, then `document.delete()`. On exception, log and re-raise.
3. **Wire** the two delete views (`views.py:200-211` and `views.py:225-237`) to call the new service. Views shrink to ~3 lines.

**Commit:** `refactor(documents): extract delete_document_with_chunks service with atomic ordering`.

### 2.2 Decide on `DocumentDeleteView` vs `StaffDocumentDeleteView` (audit H2, M7, L18)

**Decision required from the user** before tests are written. Use `AskUserQuestion` to pick one of:
- (a) Drop `DocumentDeleteView`, require staff for all deletes (recommended — matches the URL pattern's apparent intent).
- (b) Keep both, but make `DocumentDeleteView` enforce `LoginRequiredMixin` + `IsOwner` permission.

Once decided:
- If (a): delete `DocumentDeleteView`, update `urls.py:27` and `templates/documents/history.html:31` to point at the staff URL, and remove the now-redundant view.
- If (b): add `LoginRequiredMixin`, add a `Document.owner` FK (if not present; check `models.py`), and write the permission tests.

This also collapses the L18 finding ("95% identical views") for free.

**Commit:** `refactor(documents): consolidate delete views behind single auth-gated path`.

---

## Phase 3 — View → service consolidation (audit H5, M2, M3, L11)

**Why fourth:** Now that the low-level services are atomic, it's safe to extract the cross-view "pipeline" functions. The view layer becomes thin adapters.

### 3.1 Extract `query_pipeline.run_query` (audit H5)

**New file:** `policyiq/queries/services/query_pipeline.py`.

**Public API:**
```python
@dataclass
class QueryResult:
    kind: Literal["answer", "no_information"]
    answer_stream: Iterator[str] | None = None
    citations: list[dict] = field(default_factory=list)
    duration_s: float = 0.0

def run_query(question: str, document_id: str | None, *,
              top_k: int, threshold: float) -> QueryResult: ...
```

**TDD steps:**
1. **Failing tests** in `policyiq/queries/tests/test_query_pipeline.py` (new file):
   - `test_run_query_returns_no_information_when_retriever_returns_empty` — mocks `retrieve_chunks` to return `[]`, asserts `QueryResult.kind == "no_information"`.
   - `test_run_query_returns_no_information_when_chunks_below_threshold` — mocks to return chunks with `similarity_score=0.3`, asserts `"no_information"`.
   - `test_run_query_streams_tokens_and_carries_citations` — mocks to return 2 chunks above threshold and a `_generate_response` that yields 3 tokens, asserts the iterator yields the 3 tokens and `result.citations` is populated.
   - `test_run_query_uses_settings_for_top_k_and_threshold` — patches `settings.RETRIEVAL_TOP_K` / `settings.SIMILARITY_THRESHOLD`, asserts they're passed to `retrieve_chunks`.
2. **Implement** `run_query` to call `retrieve_chunks`, then `build_prompt` (which already returns `None` for "no information"), then `generate_response`. Wrap the streaming in a small adapter (see 3.2).
3. **Refactor** `QueryAPIView.post` and `AskPageView.post` to call `run_query` and translate the `QueryResult` into the response format. Delete the duplicated bodies.

**Commit:** `refactor(queries): extract run_query service, collapse QueryAPIView and AskPageView`.

### 3.2 Wrap `generate_response` to surface mid-stream errors (audit H6)

**File:** `policyiq/queries/services/generator.py:104-127`.

**TDD steps:**
1. **Failing tests** in `policyiq/queries/tests/test_generator.py`:
   - `test_streaming_wrapper_yields_error_marker_on_generation_error` — mocks the inner generator to yield 2 tokens then raise `GenerationError`, asserts the wrapper yields the 2 tokens then `<!-- error: ... -->` (or a structured sentinel you choose).
   - `test_streaming_wrapper_does_not_swallow_exception` — asserts the logger captures an ERROR line and the exception is re-raised *after* yielding the marker.
2. **Implement** a small `safe_stream(iterator) -> Iterator[str]` wrapper. Decide on a wire format (raw sentinel string vs. SSE `event: error`). For HTMX, a sentinel comment is simplest — the front-end can `querySelector` for it.
3. **Wire** `run_query` to wrap its `generate_response` iterator with `safe_stream`.

**Commit:** `fix(generator): surface mid-stream errors via sentinel marker, no silent truncation`.

### 3.3 Extract `documents.pipeline.ingest_uploaded_pdf` (audit M2, L11)

**File:** `policyiq/documents/services/pipeline.py`.

**TDD steps:**
1. **Failing tests** in `policyiq/documents/tests/test_pipeline.py` (new section `IngestUploadedPdfTests`):
   - `test_ingest_uploaded_pdf_owns_temp_file_lifecycle` — passes an `InMemoryUploadedFile`, asserts the temp file is deleted on success and on failure.
   - `test_ingest_uploaded_pdf_creates_document_and_ingests` — asserts a `Document` row exists and `ingest_document` was called with the right `document_id`.
   - `test_ingest_uploaded_pdf_rolls_back_document_on_validation_error` — passes a non-PDF, asserts no `Document` row created.
2. **Implement** `ingest_uploaded_pdf(upload_file, username=None) -> Document` that owns the `default_storage` lifecycle and `Document.objects.create` call, then delegates to `ingest_document(document, file_path)`.
3. **Refactor** `_save_upload_and_ingest` to a one-liner that calls the new function. Both upload views (HTML + API) call the same path.

**Commit:** `refactor(pipeline): extract ingest_uploaded_pdf, collapse upload views`.

### 3.4 Extract `_process_uploads` (audit L11, follow-up)

The HTML `UploadPageView` and API `DocumentUploadAPIView` still duplicate the per-file loop. Extract `_process_uploads(uploads) -> tuple[list[dict], int]` in a new `policyiq/documents/views/_uploads.py` (or in `pipeline.py`).

**TDD steps:** same shape as the integration tests in Phase 4 — write them first, then implement.

**Commit:** `refactor(documents): extract _process_uploads, collapse upload views to adapters`.

---

## Phase 4 — Test coverage (audit H7, H8, M7, M9, M10, M11, M12, M14, L1, L8, L11, L13)

**Why fifth:** By now the services have a stable shape. The remaining audit items are mostly "no test for this path." Each test is small; batch them in a single phase so reviewers see one PR per test category.

### 4.1 End-to-end "Ollama down at query time" (audit H7)

**New file:** `policyiq/queries/tests/test_views_ollama_down.py` (or append to `test_views.py`).

Tests:
- `QueryAPIViewOllamaDownTests::test_returns_502_when_ollama_unreachable` — patches `policyiq.ollama.post_json` (or `requests.post`, depending on what survived Phase 0.2) to raise `RequestException`. Asserts: status 502, body contains a human-readable error, no `X-Citations` header, `queries.views` logger captures an ERROR line.
- `QueryAPIViewOllamaDownTests::test_returns_502_when_ollama_returns_error_envelope` — patches to return 200 with `{"error": "..."}`. Asserts same.
- `AskPageViewOllamaDownTests::test_renders_error_in_html` — same as above, but POSTs to the HTML endpoint and asserts the response body contains the error message and a closing `</div>` (so the page is not half-rendered).

**Commit:** `test(queries): integration coverage for Ollama down at query time`.

### 4.2 Empty / low-similarity query path (audit H8)

Append to `policyiq/queries/tests/test_views.py::QueryAPIViewTests`:
- `test_returns_200_with_no_information_when_chroma_empty` — mocks `retrieve_chunks` to return `[]`. Asserts status 200, body `{"answer": "No relevant information found."}`, no `X-Citations` header, `generate_response` not called.
- `test_returns_200_with_no_information_when_chunks_below_threshold` — returns a chunk with `similarity_score=0.3`. Same assertions.

**Commit:** `test(queries): cover empty-ChromaDB and below-threshold paths`.

### 4.3 `DocumentDeleteView` (now consolidated) tests (audit M7)

After Phase 2.2's decision, write tests in `policyiq/documents/tests/test_views.py`:
- `test_authenticated_owner_can_delete` (or `test_staff_can_delete` if you went with option (a)).
- `test_unauthenticated_user_gets_redirect_to_login` (or `test_non_staff_gets_403`).
- `test_delete_calls_service_and_returns_redirect`.
- `test_delete_failure_renders_500` (or rolls back cleanly if you made the service atomic).

**Commit:** `test(documents): cover consolidated delete view auth and lifecycle`.

### 4.4 Reindex failure path (audit M9)

Append to `policyiq/documents/tests/test_views.py::StaffDocumentReindexViewTests`:
- `test_reindex_returns_500_when_ingest_raises` — patches `ingest_document` to raise `ExtractionError`. Asserts response status 500 (or whatever the view now returns after H2's fix).
- `test_reindex_purges_old_chunks_even_on_failure` — pre-creates chunks for the document, runs reindex with a failing `ingest_document`, asserts `Chunk.objects.filter(document=document).count() == 0` after.

**Commit:** `test(documents): cover reindex failure and chunk-purge ordering`.

### 4.5 `HistoryPageView` and `HomePageView` (audit M10)

New `policyiq/documents/tests/test_views.py::HistoryPageViewTests`:
- `test_empty_db_renders_no_rows` — asserts 200, no `<tr>` for documents.
- `test_two_docs_rendered_in_reverse_chronological_order` — creates 2 documents with different `uploaded_at`, asserts the rendered order.
- `test_special_character_filename_does_not_inject_html` — creates a doc named `Aetna&2026.pdf`, asserts `&amp;` appears in the rendered HTML (i.e., `escape` is in place). **If this fails, the test is the bug report — fix the template by adding `|escape` and re-run.**

**Commit:** `test(documents): cover HistoryPageView rendering and XSS-safety`.

### 4.6 Mid-stream connection drop (audit M10)

New test in `policyiq/queries/tests/test_generator.py`:
- `test_generate_response_raises_when_ollama_drops_mid_stream` — patches the `post_stream` (or `requests.post`) to return a response whose `iter_lines` yields 2 lines then raises `ChunkedEncodingError`. Asserts `GenerationError` is raised, and (if you implemented 3.2) the wrapper yields the error marker.

**Commit:** `test(generator): cover mid-stream connection drop`.

### 4.7 Health-check `# pragma: no cover` cleanup (audit M12)

Drop the comments. Run `pytest --cov` to confirm `test_health.py` already covers the lines.

**Commit:** `chore(queries): drop stale pragma: no cover comments in health.py`.

### 4.8 Upload partial-failure matrix (audit M11)

New `policyiq/documents/tests/test_views.py::UploadPartialFailureTests`:
- `test_two_files_one_success_one_pipeline_failure_returns_201` — asserts the response is 201 and the `results` list has 2 entries, one with `success: True` and one with `success: False`.
- `test_two_files_one_success_one_validation_failure_returns_201`.
- `test_one_file_pipeline_failure_returns_500` — assert the response is 500 and the `results` list has 1 failure entry.
- `test_one_file_validation_failure_returns_400`.
- `test_upload_result_serializer_accepts_failure_shape` — instantiate `UploadResultSerializer(data={"success": False, "error": "..."})` and assert `is_valid()` is True.

**Commit:** `test(documents): cover upload partial-failure matrix and serializer shape`.

### 4.9 Other test gaps in this batch

- **L1** `MEDIA_ROOT` test override isolation: switch the `@override_settings(MEDIA_ROOT=tempfile.gettempdir())` decorators to use `tempfile.mkdtemp()` inside `setUp`/`tearDown`. Commit: `test(documents): isolate MEDIA_ROOT per test`.
- **L8** `MAX_QUESTION_LOG_CHARS` cross-module: move the constant to `policyiq/queries/constants.py`. Commit: `refactor(queries): move MAX_QUESTION_LOG_CHARS to queries/constants.py`.
- **L13** `test_views_pytest.py` duplication: pick one. Recommend deleting `test_views_pytest.py` and keeping `test_views.py`. The `conftest.py` fixtures stay. Commit: `chore(queries): drop duplicate pytest-style view tests`.
- **L11** `_process_uploads` extraction: if not already done in Phase 3.4, do it here.

---

## Phase 5 — Cleanup, dead code, and consistency (audit M1, M4, M5, M6, M13, L2, L5, L6, L10, L12, L14, L15, L16, L17, L18, L19, L20, L21)

**Why sixth:** The remaining items don't block correctness; they reduce noise and risk. Order them so each commit is small and reviewable.

### 5.1 Decide on `Chunk` storage duplication (audit M1)

**Decision required from the user.** Use `AskUserQuestion`:
- (a) Drop `Chunk.text` column (keep model for admin `page_number` / `token_offset`).
- (b) Drop `Chunk` model entirely (chunks live in ChromaDB only).
- (c) Keep both, document the rationale in `CLAUDE.md`.

After decision:
- If (a): add a `documents/migrations/0006_remove_chunk_text.py` migration, remove the field, update `admin.py` if needed, remove `Chunk.objects.bulk_create(...)` from `pipeline.py` (now redundant).
- If (b): drop the model, the migration, the admin registration, and the reindex `Chunk.objects.filter(...).delete()` (audit M5 collapses for free).
- If (c): document.

**Commit:** `refactor(documents): remove Chunk.text column` (or whichever).

### 5.2 Drop `StageTimer` / `timing.py` or adopt it (audit M4)

**Decision:** Either adopt `stage_timer` in `pipeline.py` (and the other 5 services that have inline `t0 = time.monotonic()` blocks) or delete `timing.py` and `test_timing.py`.

Recommended: **adopt** in `pipeline.py` only (the file's own logger boundary), then in a second pass the other 5 services. If you want minimum churn, **delete** `timing.py` / `test_timing.py` and add a `# TODO: shared stage timer` comment where each inline block lives.

**Commit:** `refactor(pipeline): adopt stage_timer` (or `chore(queries): drop unused stage_timer`).

### 5.3 Drop leading underscores on `_generate_ollama` / `_generate_anthropic` (audit M6)

After Phase 0.2, the HTTP code lives in `ollama.py`. The wrappers in `generator.py` can be renamed `generate_ollama` / `generate_anthropic` and the existing test can be re-routed through the public `generate_response` with `LLM_BACKEND=anthropic`.

**Commit:** `refactor(generator): drop private-name wrappers, route tests through public dispatch`.

### 5.4 Replace `_STAGE_BY_EXCEPTION_NAME` with `isinstance` ladder (audit L2)

Trivial refactor in `pipeline.py:97-114`. Existing test still passes.

**Commit:** `refactor(pipeline): isinstance-based stage classification`.

### 5.5 `OllamaClient` cache key collisions (audit L5)

Make `get_chroma_client(path: str | None = None) -> PersistentClient` take the path as a parameter so `lru_cache` keys on it. Drop the `cache_clear()` calls from test `setUp`s.

**Commit:** `refactor(indexer): path-parameterized chromadb client cache`.

### 5.6 De-duplicate log lines between views and services (audit L6)

Pick one: view logs only the "receipt" and "complete" line, services log the rest. Do this in `documents/views.py` first, then `queries/views.py`.

**Commit:** `refactor(views): collapse duplicate logging, single receipt line per request`.

### 5.7 Resolve the `MEDIA_ROOT` local-FS assumption (audit L10)

Add a comment at `settings.py:96` and at `pipeline.py:32` / `views.py:88` stating "Assumes `FileSystemStorage`; if `django-storages` is added, replace `default_storage.path()` with `default_storage.url()` or pass a stream."

**Commit:** `docs(infra): annotate local-FS storage assumption`.

### 5.8 Extract `_DynamicRateMixin` and the four throttles (audit L17)

**New file:** `policyiq/policyiq/throttles.py` with the mixin and the four subclasses. `documents/throttles.py` and `queries/throttles.py` re-export the ones they need. Tests stay in place.

**Commit:** `refactor(throttles): consolidate to project-level module`.

### 5.9 Decide on `_save_upload_and_ingest` and `_validate_pdf` (audit M3)

If Phase 3.3 extracted `ingest_uploaded_pdf`, the view is already a 5-line adapter. Drop the in-`_save_upload_and_ingest` `_validate_pdf` call (the view already validates) and add the size check to `_validate_pdf` using `PDF_MAX_BYTES`.

**Commit:** `refactor(documents): centralize PDF validation, add size check`.

### 5.10 Drop the `Chunk.objects.filter(...).delete()` in reindex (audit M4)

If Phase 5.1 went with (a) or (b), this line is now redundant — remove it. If (c), leave a one-line comment explaining it's intentional.

**Commit:** `refactor(documents): drop redundant pre-reindex chunk delete`.

### 5.11 Misc. low-priority items

- **L12** (`CHANGELOG.md` lru_cache doc): when 5.5 lands, update the changelog to match the new path-parameterized form.
- **L15** (`extract_pages` memory): file a `// TODO: stream `get_text()` for very large PDFs.` comment in `extractor.py:26-30`. No commit needed.
- **L16** (`clean_pages` two-pass): same — `// TODO: fuse with single-pass counter.` No commit.
- **L19** (`extract_pages` exception type, audit M13): wrap `FileNotFoundError` and `ValueError` in `ExtractionError` at the extractor boundary. Update the test that codified the wrong type. **Commit:** `fix(extractor): raise domain ExtractionError consistently`.
- **L20** (`/api/tags` health endpoint): done implicitly by Phase 0.2's `ollama_client.ping()`.
- **L21** (`clean_pages`, `extract_pages` deferred): already filed under L15/L16.

---

## Phase 6 — Verify, log, tag

After all five phases, do a final pass:

1. **Run the full test suite:** `pytest -x --cov`. Confirm coverage is non-decreasing and all tests pass.
2. **Manual smoke:** upload a PDF, run a query that hits the answer branch, run a query that hits the "no information" branch, run a query with Ollama down, hit `/healthz/`. Confirm logs are clean and not noisy.
3. **Update `docs/CHANGELOG.md`** with a single entry: `## Refactor pass — closes all findings in docs/REFACTOR_AUDIT.md` and a bullet list of phase summaries.
4. **Update `CLAUDE.md`** with the decision from Phase 5.1 (where chunks live).
5. **Tag the release.**

---

## Dependency graph (compact)

```
Phase 0 (settings + ollama_client)
   ↓
Phase 1 (pipeline atomicity)
   ↓
Phase 2 (delete atomicity + DocumentDeleteView consolidation)
   ↓
Phase 3 (view → service: run_query, ingest_uploaded_pdf, _process_uploads, safe_stream)
   ↓
Phase 4 (test coverage batch)
   ↓
Phase 5 (cleanup, dead code, dedup, doc fixes)
   ↓
Phase 6 (verify, log, tag)
```

Each phase is independently mergeable. If you want to ship sooner, the minimum viable slice that closes the **High** findings is **Phases 0 + 1 + 2 + 3.1 + 3.2** (the rest can follow in follow-up PRs).

---

## Open decisions for the user

These need an answer before the matching phase can start; everything else has a sensible default.

1. **Phase 5.1 — Chunk storage duplication:** drop `Chunk.text`, drop `Chunk` entirely, or keep both? Default: drop `Chunk.text` (keeps the relational model, removes the duplication).
2. **Phase 2.2 — `DocumentDeleteView` consolidation:** drop the public view (staff only) or keep it with `LoginRequiredMixin` + owner check? Default: drop (the public path looks accidental).
3. **Phase 5.2 — `StageTimer`:** adopt in services or delete? Default: delete (simpler; the inline blocks are clear enough).
4. **Phase 5.13 — `test_views_pytest.py`:** keep pytest-style and remove `test_views.py`, or the reverse? Default: keep `test_views.py` (Django `TestCase` is the project standard per `AGENTS.md`).
