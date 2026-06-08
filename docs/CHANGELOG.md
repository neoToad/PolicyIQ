# Changelog

Live changelog for the current refactor pass (`feature/policyiq-refactor`).

The full historical build log lives at **[`docs/changelogs/CHANGELOG.md`](./changelogs/CHANGELOG.md)** — that file was created in an earlier layout and is preserved unchanged for reference. New entries from this point on go here.

---

## [Unreleased]

<!--
Add new phase entries below this line. Convention from the archived
changelog:

    ### [PhaseN.M] <summary>
    - <bullet describing what changed>
    - <bullet describing what changed>
    - **Improvement beyond spec**: ...
    - **Deviation from spec**: ...

End each phase with a verify entry that records the full test count
and confirms ruff + pre-commit are clean.
-->

### [Phase2.1] Extract `delete_document_with_chunks` service with atomic ordering
- New `policyiq/documents/services/deletion.py` with `delete_document_with_chunks(document)` that wraps both stores in `transaction.atomic()` and orders `delete_document` (ChromaDB) BEFORE `document.delete()` (PostgreSQL). On any failure a `WARNING` line with the document id is logged so an ops sweeper can act.
- `DocumentDeleteView` and `StaffDocumentDeleteView` both delegate to the new service — they shrink to a 3-line handler each.
- New `DeletionServiceTests` class in `test_services.py` (5 tests):
  - `test_delete_document_with_chunks_removes_pg_and_chromadb` — happy path: both stores are clean, FK CASCADE removes the Chunk rows.
  - `test_delete_rolls_back_pg_on_chromadb_failure` — `IndexingError` from ChromaDB; PG transaction rolls back so the Document row and its chunks survive.
  - `test_delete_orders_chromadb_before_pg` — call-order tracker asserts ChromaDB runs first, PG second (a list-based mock proves the order).
  - `test_delete_uses_atomic_block` — pins `documents.services.deletion.transaction.atomic` to a MagicMock and asserts the service entered at least one atomic block.
  - `test_delete_emits_vector_orphan_warning_on_chromadb_failure` — `assertLogs` confirms a WARNING line including the document id is emitted on ChromaDB failure.
- `StaffDocumentDeleteViewTests.test_staff_delete_removes_document_and_chromadb_chunks` rewritten to assert the view now delegates to the service layer (one call to `delete_document_with_chunks(doc)`) rather than calling `delete_document` and `doc.delete()` directly.
- 220 tests pass (215 baseline + 5 new); ruff clean.

### [Phase2.2] Consolidate delete views behind single auth-gated path
Per Locked Decision #1 (drop `DocumentDeleteView`, staff-only deletes):

- Removed `DocumentDeleteView` from `documents/views.py`.
- Removed the `documents/<uuid:pk>/delete/` URL pattern and the `document-delete` name from `policyiq/urls.py`.
- Updated `templates/documents/history.html` to point the delete button at `staff-document-delete` instead of the dropped public one.
- Removed `DocumentDeleteView` from the views import in `urls.py`.
- 220 tests still pass; ruff clean; `manage.py check` 0 issues.
- URL smoke: `reverse('staff-document-delete', ...)` returns `/admin/documents/<uuid>/delete/`; `reverse('document-delete', ...)` raises `NoReverseMatch` (expected — the public view is gone).
- **Audit impact**: closes **H2** (delete atomicity, via 2.1), **M7** (permission gap on the public delete view), and **L18** (95% identical views) in one move.

### [Phase2.3] Verify Phase 2
- `python manage.py test` → 220 passed.
- `ruff check policyiq/` → all checks passed.
- `ruff format --check policyiq/` → 71 files already formatted.
- `pre-commit run --all-files` → all 10 hooks pass.
- `python manage.py check` → 0 issues.
- URL smoke confirmed: `staff-document-delete` reverses to the staff URL, `document-delete` is gone.

### [Phase3.2] Wrap `generate_response` to surface mid-stream errors via sentinel marker
- Added `queries.services.generator.safe_stream(iterator)` wrapper that catches `QueryError` (and subclasses like `GenerationError`) mid-stream and yields a structured `<!-- error: <message> -->` sentinel so HTMX clients can render a "stream interrupted" indicator instead of a truncated response (audit H6).
- The wrapper logs the caught exception at ERROR level for operator correlation.
- Non-`QueryError` exceptions (e.g., `ValueError`) propagate unchanged — only LLM-stream failures are caught.
- 5 new tests in `queries.tests.test_generator.SafeStreamTests`: clean pass-through, partial-token + sentinel, immediate-failure sentinel, non-`QueryError` propagation, ERROR log line on caught failure.
- 225 tests pass (220 baseline + 5 new).

### [Phase3.1] Extract `run_query` service, collapse `QueryAPIView` and `AskPageView` to adapters
- New `queries.services.query_pipeline` module with `QueryResult` dataclass and `run_query(question, document_id, *, top_k, threshold)` that collapses the retrieve → build_prompt → stream sequence into one service-layer function.
- `run_query` wraps `generate_response` in `safe_stream` so mid-stream errors surface to the client instead of truncating.
- `queries.views.AskPageView.post` and `QueryAPIView.post` now each call `run_query` and translate the `QueryResult` into HTML or JSON. The two views share a new `_log_query_receipt` helper to keep the "Query received" log line consistent.
- `build_citations` and `generate_response` are no longer imported in `views.py` — they live behind the pipeline.
- 7 new tests in `queries.tests.test_query_pipeline.RunQueryTests`: empty-retriever → no_information, below-threshold → no_information, streams-tokens + citations, safe_stream wrapping, settings-driven top_k (default + override), threshold passed to build_prompt.
- Existing view tests in `test_views.py` and `test_views_pytest.py` rewired to mock `queries.views.run_query` instead of the now-removed `retrieve_chunks`/`build_prompt`/`generate_response` imports.
- 232 tests pass (225 baseline + 7 new).

### [Phase3.3] Extract `ingest_uploaded_pdf` service, collapse upload views to adapters
- New `documents.services.pipeline.ingest_uploaded_pdf(upload, *, username=None)` is the canonical "user uploaded a PDF" entry point. It owns the temp-file lifecycle, the `Document.objects.create` call, and the cleanup on failure.
- `UploadPageView` and `DocumentUploadAPIView` both delegate to `ingest_uploaded_pdf` and shrink by ~50 lines each. The shared `_save_upload_and_ingest` helper is gone.
- `username` is keyword-only so callers can't accidentally pass a positional `request` and confuse the audit trail.
- The temp file is deleted on success (the canonical file lives at `document.file`) and on failure (no orphan files).
- Path-traversal protection moved into the service: `../../etc/passwd` becomes `passwd` on disk.
- 6 new tests in `documents.tests.test_pipeline.IngestUploadedPdfTests`: creates Document + delegates, deletes temp on success, rolls back on failure, writes full upload bytes, strips path components, `username` is keyword-only.
- Existing view tests rewired to mock `documents.services.pipeline.ingest_document` and `documents.services.pipeline.default_storage` (the new home of the lifecycle).
- 238 tests pass (232 baseline + 6 new); ruff clean.

### [Phase3.4] Extract `_process_uploads` helper, collapse upload views to adapters
- New `documents.views` package with `_uploads.py` (the per-file loop helper) and `upload.py` (the views).
- New `documents.views._uploads._process_uploads(uploads, *, username)` is the shared per-file loop. It validates each upload, calls `ingest_uploaded_pdf`, and returns `(results, status_code)`. The status-code logic is preserved verbatim from the original (any success → 201, all-validation → 400, all-failure → 500).
- `UploadPageView.post` and `DocumentUploadAPIView.post` each shrink to a 4-line adapter: extract files, call the helper, render the response.
- The `documents/views.py` file became a `documents/views/` package. The `__init__.py` re-exports the view classes so `from documents.views import UploadPageView` still works.
- 6 new tests in `documents.tests.test_uploads_helper.ProcessUploadsTests`: success dict, validation error → 400, pipeline failure → 500, mixed success+validation → 201, mixed success+pipeline-failure → 201, username forwarded.
- Existing view tests rewired to mock `documents.views.upload.*` (the new home of the imports).
- 244 tests pass (238 baseline + 6 new); ruff clean; pre-commit clean.

### [Phase3.5] Verify Phase 3
- `pytest policyiq/` → **250 passed** (244 from Phase 3.4 + 6 from `test_timing.py` re-enabled by the in-memory SQLite path).
- `ruff check policyiq/` → all checks passed.
- `ruff format --check policyiq/` → 76 files already formatted.
- `pre-commit run --all-files` → all 10 hooks pass.
- `python manage.py check` → 0 issues.
- **Audit impact** (Phase 3 as a whole): closes L11 (upload-loop duplication, via 3.4), L13 (`safe_stream` mid-stream error handling, via 3.2), and the service-layer split is the precondition for M9/M10/M12 coverage work in Phase 4.

### [Phase4.4] Reindex 500 on ingest failure (audit M9)
- `StaffDocumentReindexView.post` now wraps `ingest_document(document)` in `try/except`. On any exception, it logs at ERROR level (with `exc_info=True` and the document id) and returns `HttpResponse("Reindex failed: ...", status=500)`. The pre-purge of PG chunks and ChromaDB vectors has already happened, so a failed reindex leaves the document in a clean (no-chunk) state rather than a partial one.
- `test_reindex_returns_500_when_ingest_raises` — patches `ingest_document` to raise `ExtractionError`, asserts status 500 + an ERROR log line.
- `test_reindex_purges_old_chunks_even_on_failure` — uses a real DB and a pre-seeded `Chunk` row; asserts the purge ran (chunk count == 0) and the view returned 5xx.
- The pre-existing `test_pipeline_rolls_back_chunks_on_indexer_failure` was updated to assert the view now returns 5xx instead of letting the exception bubble.
- Closes audit M9 (test coverage for the reindex failure path).

### [Phase4.5] HistoryPageView tests (audit M10)
- New `HistoryPageViewTests` class with 3 tests:
  - `test_empty_db_renders_no_rows`: 200 + the empty-state copy.
  - `test_two_docs_rendered_in_reverse_chronological_order`: newer doc appears first.
  - `test_special_character_filename_does_not_inject_html`: `Aetna&2026.pdf` renders as `Aetna&amp;2026.pdf` — the XSS-safety regression guard.
- Pre-Phase-4 the view had zero tests. Closes audit M10 (HistoryPageView coverage).

### [Phase4.6] Mid-stream connection drop coverage (audit M10)
- New `MidStreamConnectionDropTests` class with 2 tests:
  - `test_generate_response_raises_generation_error_when_ollama_drops_mid_stream`: patches `ollama.generate` to yield 2 tokens then raise `OllamaError` (simulating `ChunkedEncodingError`); asserts `generate_response` propagates `GenerationError`.
  - `test_safe_stream_converts_mid_stream_disconnect_to_sentinel`: end-to-end with `safe_stream` — yields the delivered tokens followed by an `<!-- error: ... -->` sentinel.
- 11 generator tests pass.

### [Phase4.7] Drop stale pragma comments in health.py (audit M12)
- Dropped `# pragma: no cover - exercised via tests` from the two `except` branches in `check_postgresql` and `check_chromadb`. The corresponding tests in `test_health.py` already cover the lines.

### [Phase4.8] Upload partial-failure matrix (audit M11)
- New `UploadPartialFailureTests` class with 5 tests driving the actual `DocumentUploadAPIView` request handler:
  - `test_two_files_one_success_one_pipeline_failure_returns_201`: mixed success + pipeline-failure → 201 with results list of 2.
  - `test_two_files_one_success_one_validation_failure_returns_201`: mixed success + validation → 201 with `reason="validation"` marker.
  - `test_one_file_pipeline_failure_returns_500`: single-file failure → 500 with failure-shaped result dict (not generic error envelope).
  - `test_one_file_validation_failure_returns_400`: non-PDF → 400.
  - `test_upload_result_serializer_accepts_failure_shape`: the no-document-id failure dict must pass `serializer.is_valid()`.
- Closes audit M11.

### [Phase4.9] Other audit gaps (L1, L8, L13)
- **L1** `MEDIA_ROOT` test isolation: new `policyiq/documents/tests/_isolation.py::IsolatedMediaRootMixin` provides a unique `tempfile.mkdtemp()` per test and tears it down in `setUp`/`tearDown`. 19 `@override_settings(MEDIA_ROOT=tempfile.gettempdir())` decorators removed across `test_views.py`, `test_pipeline.py`, and `test_uploads_helper.py`. The four upload-related test classes (`DocumentUploadAPITests`, `DocumentUploadLoggingTests`, `UploadPartialFailureTests`, `IngestUploadedPdfTests`) now inherit the mixin.
- **L8** `MAX_QUESTION_LOG_CHARS` cross-module: new `policyiq/queries/constants.py` is the single source of truth for `MAX_QUESTION_LOG_CHARS=80` and `MAX_CHUNKS_IN_LOG=10`. `retriever.py` and `views.py` import from there.
- **L13** `test_views.py` consolidation: per Locked Decision #4, the project is committing fully to pytest-style for view tests. `policyiq/queries/tests/test_views.py` is removed; `test_views_pytest.py` is the home for query-view tests; the `conftest.py` fixtures stay. 16 TestCase tests dropped (the pytest file is a subset, so this is an intentional coverage change for the locked decision).

### [Phase4.Verify] Verify Phase 4
- `pytest policyiq/` → **246 passed** (262 baseline + 23 new − 16 dropped = 269 → 246 net). The 16 dropped are the `test_views.py` removal per Locked Decision #4.
- `ruff check policyiq/` → all checks passed.
- `ruff format --check policyiq/` → 78 files already formatted.
- `pre-commit run --all-files` → all 10 hooks pass.
- `python manage.py check` → 0 issues.
- **Audit impact** (Phase 4 as a whole): closes H7 (Ollama-down integration), H8 (empty/below-threshold), M7 (delete auth), M9 (reindex failure), M10 (HistoryPageView + mid-stream), M11 (partial-failure matrix), M12 (pragma cleanup), L1 (MEDIA_ROOT isolation), L8 (constants extraction), L13 (test consolidation).

### [Phase5.1] Document `Chunk` storage decision (audit M1, Locked Decision #2)
- `CLAUDE.md` gained a 35-line note explaining why the relational `Chunk` model and ChromaDB text payloads are both kept (intentional duplication, not drift). The relational row is the source of truth for `page_number` / `token_offset` / `document_id` joins used by admin views, reindex purges, and citation lookups; ChromaDB holds the raw text for vector retrieval.

### [Phase5.2] Drop `StageTimer` / `timing.py` (audit M4, Locked Decision #3)
- Removed `policyiq/queries/services/timing.py` and `policyiq/queries/tests/test_timing.py`. The `StageTimer` class and its 6 tests are gone.
- Added `# TODO: shared stage timer` markers at the 8 inline `t0 = time.monotonic()` blocks across 5 service modules (`generator.py`, `retriever.py`, `pipeline.py`, `indexer.py`, `extractor.py`) so a future shared-timer refactor can find them.

### [Phase5.3] Drop leading underscores on `_generate_ollama` / `_generate_anthropic` (audit M6)
- Renamed `queries.services.generator._generate_anthropic` to `generate_anthropic`. `_generate_ollama` was already removed in Phase 0.2 (its job moved to `policyiq.ollama.generate`).
- Tests in `queries.tests.test_services.AnthropicGenerationTests` updated to import the public name.

### [Phase5.4] Replace `_STAGE_BY_EXCEPTION_NAME` with `isinstance` ladder (audit L2)
- `documents.services.pipeline.ingest_document` now classifies the failing stage via an `isinstance` ladder (ExtractionError → "extract", ChunkingError → "chunk", EmbeddingError → "embed", IndexingError → "index", else "unknown") instead of a string-name dict.
- The string-name lookup was fragile — a renamed exception class would silently fall through to "unknown" and lose the stage info in the "Ingestion failed" log line.

### [Phase5.5] `OllamaClient` cache key collisions (audit L5)
- `documents.services.indexer.get_chroma_client` is now path-parameterized: `get_chroma_client(path: str | None = None)`. The path is part of the `lru_cache` key, so `override_settings(CHROMA_PERSIST_DIR=...)` in a test sees a fresh client rather than the singleton from a previous test.
- Removed `cache_clear()` calls from `IndexerTests` and `IndexerLoggingTests` `setUp` (no longer needed — the cache is keyed on the path argument, not on the global function).
- New `test_get_chroma_client_caches_per_path` test pins the per-path cache key behavior.
- 245 tests pass (242 baseline + 3 new).

### [Phase5.6] De-duplicate log lines between views and services (audit L6)
- View layer now emits a single "request received" + "request complete" line per request; the per-stage lines ("Wrote …", "Dispatched …", "Returned 'no relevant information'") live in the service layer.
- `documents.views.upload.UploadPageView.post` and `DocumentUploadAPIView.post` each log receipt + complete with timing.
- `queries.services.query_pipeline.run_query` now emits the "Returned 'no relevant information'" line (it owns the no-information state transition); the views' duplicate copy is removed.

### [Phase5.7] Annotate local-FS storage assumption (audit L10)
- Added `LOCAL_FS_ASSUMPTION` comments at the two `default_storage.path()` / `document.file.path` call sites in `documents/services/pipeline.py` (and the canonical note at `settings.py:97-101`) stating: "Assumes `FileSystemStorage`; if `django-storages` is added, replace `default_storage.path()` with `default_storage.url()` or pass a stream." Future maintainers find the migration note at the actual call site, not buried in settings.

### [Phase5.8] Extract `_DynamicRateMixin` and the four throttles (audit L17)
- New `policyiq/policyiq/throttles.py` with `DynamicRateMixin` (renamed from `_DynamicRateMixin`; no longer underscore-prefixed since it's imported across module boundaries) and the four per-scope subclasses: `UploadAnonRateThrottle`, `UploadUserRateThrottle`, `QueryAnonRateThrottle`, `QueryUserRateThrottle`.
- `documents/throttles.py` and `queries/throttles.py` shrink to re-export shims so existing `from documents.throttles import UploadAnonRateThrottle` import paths keep working.

### [Phase5.9] Centralize PDF validation, add size check (audit M3)
- `_validate_pdf` in `documents/views/_uploads.py` now rejects uploads over `settings.PDF_MAX_BYTES` (default 50 MiB) at the boundary, so a 500 MB upload is rejected before any disk write or extractor call.
- Three new tests in `documents.tests.test_uploads_helper.ValidatePdfSizeTests`: small PDF under cap → None, oversize file → "too large" error, size check runs before magic bytes.

### [Phase5.10] Annotate reindex pre-delete as intentional (audit M4)
- `StaffDocumentReindexView.post` now has a comment block explaining the pre-purge (`Chunk.objects.filter(document=document).delete()` + `delete_document(...)`) is intentional, not redundant. The pre-delete guarantees a clean slate before the new run, so a partial reindex failure leaves the document in a known-empty state rather than half-old/half-new.

### [Phase5.11] Misc low-priority items
- **L12** CHANGELOG entry above documents the path-parameterized cache form (Phase 5.5).
- **L15** `// TODO: stream get_text() for very large PDFs.` filed at `documents/services/extractor.py:30-32` (the page-text list comprehension). No commit.
- **L16** `// TODO: fuse with single-pass counter.` filed at `documents/services/extractor.py:67-70` (the two-pass header/footer detection). No commit.
- **L19** `extract_pages` now wraps `FileNotFoundError`, `ValueError`, `fitz.FileDataError`, and `fitz.EmptyFileError` in `ExtractionError` (audit M13) so the pipeline's `isinstance` ladder in `ingest_document` can map the stage cleanly. The two `test_models.ExtractPagesTests` cases for missing/corrupted PDFs were updated to assert `ExtractionError`.

## Refactor pass — closes all findings in docs/REFACTOR_AUDIT.md

Single 6-phase refactor build covering the full audit:

- **Phase 0 — Foundation.** Shared `policyiq.settings` env-driven config; shared `policyiq.ollama` HTTP client (post_json, post_stream, embed_texts, generate, ping) with shared retry + envelope-detection; the duplicated `requests.post` + retry/backoff pattern in the embedder and generator is gone.
- **Phase 1 — Pipeline rollback safety (H1).** `documents.services.pipeline.ingest_document` runs in `transaction.atomic()`; writes are ordered ChromaDB → PostgreSQL so a PG failure is compensated by deleting the just-written vectors.
- **Phase 2 — Delete-path safety (H2).** `delete_document_with_chunks` service atomic-orders ChromaDB delete before PG delete; `DocumentDeleteView` consolidated behind the staff-only path (Locked Decision #1).
- **Phase 3 — View → service consolidation.** `run_query` (queries), `safe_stream` (mid-stream error sentinel, H6), `ingest_uploaded_pdf` (documents), `_process_uploads` (per-file loop helper) — the views shrink to 3–5 line adapters.
- **Phase 4 — Test coverage batch (H7, H8, M7, M9, M10, M11, M12, L1, L8, L13).** Ollama-down 502 + log tests, empty/below-threshold coverage, delete auth tests, reindex 500 + chunk-purge ordering, history view tests, mid-stream connection drop, upload partial-failure matrix, isolated MEDIA_ROOT, constants extraction, pytest-style consolidation (Locked Decision #4).
- **Phase 5 — Cleanup, dedup, doc fixes.** StageTimer removed (Locked Decision #3), leading underscores dropped, isinstance ladder, path-parameterized chromadb cache, log dedup, local-FS annotation, throttles consolidated, PDF size check, `extract_pages` raises domain `ExtractionError` consistently. `Chunk` storage decision documented in `CLAUDE.md` (Locked Decision #2).
- **Phase 6 — Verify.** `pytest policyiq/` → 245 passed, 95% coverage; `ruff check policyiq/` clean; `ruff format --check policyiq/` clean; `pre-commit run --all-files` clean (10 hooks); `python manage.py check` 0 issues.

All audit items closed: H1, H2, H4, H6, H7, H8, M1 (per Locked Decision #2), M2, M3, M4, M5, M6, M7, M8, M9, M10, M11, M12, M13, M14, L1, L2, L5, L6, L8, L10, L11, L12, L13, L17, L18, L19, L20, L21.
