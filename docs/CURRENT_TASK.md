# Current Task

**Phase 3 COMPLETE — view → service consolidation. Phase 4 starting: test coverage batch.**

> **Note on changelog layout (2026-06-07):** The historical changelog was moved to `docs/changelogs/CHANGELOG.md`. The new top-level `docs/CHANGELOG.md` is the live file for Phase 2+ entries; it points to the archive in its header.

## Status
- Branch `feature/policyiq-refactor` checked out from `main`
- Phase 0 fully complete (settings + ollama_client + per-module migrations)
- Phase 1 fully complete (pipeline atomicity + vector-orphan marker)
- Phase 2 fully complete (deletion service + view consolidation)
- **Phase 3 fully complete** — `run_query`, `safe_stream`, `ingest_uploaded_pdf`, `_process_uploads` all extracted
- **Phase 4 starting** — test coverage batch (audit H7, H8, M7, M9, M10, M11, M12, M14, L1, L8, L11, L13)
- 4 user decisions locked in:
  1. **Phase 2.2**: Drop `DocumentDeleteView`, staff-only deletes (matches default)
  2. **Phase 5.1**: **KEEP both** (PG `Chunk` model + ChromaDB text) — user override from default; document the rationale in `CLAUDE.md`
  3. **Phase 5.2**: Delete `queries/services/timing.py` and `queries/tests/test_timing.py` (matches default)
  4. **Phase 4.9**: **KEEP `test_views_pytest.py`, drop `test_views.py`** — user override from default; commit fully to pytest-style

## Phase 0 — done
- **0.1**: 16 env-overridable settings in `settings.py`; `policyiq.llm_config` URL helpers; per-module settings wiring for embedder/generator/chunker/retriever/views/similarity context processor
- **0.2**: `policyiq/ollama.py` shared client with `post_json`, `post_stream`, `embed_texts`, `embed_query`, `generate`, `ping`, `is_error_envelope`, `validate_embedding_vector`; `OllamaError` base with `EmbeddingError`/`GenerationError` aliases
- **0.2c/d/e**: embedder, generator, health now delegate to the shared client — one retry policy, one error-envelope contract
- **0.3**: Full suite green (215 tests), ruff clean, `manage.py check` clean, live smoke test of `/api/health/`, `/`, `/ask/`, `/upload/`, `/history/`, `/admin/` all return expected codes

## Phase 1 — done
- **1.1**: `documents/services/pipeline.py::ingest_document` now wraps its body in `transaction.atomic()`. Writes are reordered: `index_document` (ChromaDB) runs BEFORE `Chunk.objects.bulk_create` (PostgreSQL). On a `bulk_create` failure, `delete_document(document_id)` is called to compensate the vector store. A 5-test `AtomicityTests` class in `documents/tests/test_pipeline.py` proves: chunks rolled back on indexer failure, vectors compensated on bulk_create failure, `transaction.atomic` is used as a context manager, reindex view leaves zero orphan chunks on failure, bulk_create is not attempted if indexer fails first. The legacy `PipelineLoggingTests` migrated from `SimpleTestCase` to `TestCase` so the new atomic block can run against an in-memory SQLite DB.
- **1.2**: Vector-orphan warning marker. When `bulk_create` fails AND the compensating `delete_document` also fails, the pipeline emits a `WARNING` line containing `Vector orphan`, the `document_id`, and the `chunk_count` so a follow-up ops sweeper can find and clean up the leftover vectors. Locked in by a new test (`test_vector_orphan_warning_fires_when_compensation_fails`).
- **1.3**: Verification — `python manage.py test` → 215 passed; `ruff check policyiq/` clean; `ruff format --check policyiq/` clean (70 files); `pre-commit run --all-files` clean; `python manage.py check` → 0 issues.
- **1.4**: Archived the historical changelog. The full 732-line build log moved to `docs/changelogs/CHANGELOG.md` (git mv, history preserved). New top-level `docs/CHANGELOG.md` is a 23-line live file with a pointer to the archive.

## Phase 2 — done
- **2.1**: New `documents/services/deletion.py::delete_document_with_chunks(document)` wraps both stores in `transaction.atomic()`, orders `delete_document` (ChromaDB) BEFORE `document.delete()` (PostgreSQL), and logs a `WARNING` line with the document id on any failure. New 5-test `DeletionServiceTests` class in `test_services.py` proves: happy path removes both stores, PG rolls back on ChromaDB failure, ordering is correct, atomic block is used, warning is emitted on failure. Both `DocumentDeleteView` and `StaffDocumentDeleteView` now delegate to the new service. The existing `StaffDocumentDeleteViewTests` was rewritten to assert the new wiring.
- **2.2**: Dropped `DocumentDeleteView` (Locked Decision #1). All delete traffic goes through the staff-only path. `policyiq/urls.py` lost the `documents/<uuid:pk>/delete/` URL and the `document-delete` name; `templates/documents/history.html` now points the delete button at `staff-document-delete`. Net diff: 16 lines deleted, 1 line added. This closes audit H2 (delete atomicity, via 2.1), M7 (permission gap on the public delete view), and L18 (95% identical views) in one move.
- **2.3**: Verification — `python manage.py test` → 220 passed (215 baseline + 5 new `DeletionServiceTests`); `ruff check policyiq/` clean; `ruff format --check policyiq/` clean (71 files); `pre-commit run --all-files` clean; `python manage.py check` → 0 issues. URL smoke: `reverse('staff-document-delete', ...)` returns `/admin/documents/<uuid>/delete/`; `reverse('document-delete', ...)` raises `NoReverseMatch` (expected — the public view is gone).

## Phase 3 — done
- **3.1**: Extracted `queries.services.query_pipeline.run_query(question, document_id, *, top_k, threshold) -> QueryResult` collapsing retrieve → build_prompt → stream into one service call. `AskPageView` and `QueryAPIView` are now thin adapters (4-7 lines each) that translate `QueryResult` into HTML or JSON. 7 new `RunQueryTests` in `test_query_pipeline.py`; view tests rewired to mock `queries.views.run_query`. 232 tests pass.
- **3.2**: Wrapped `generate_response` with `queries.services.generator.safe_stream(iterator)`. Catches `QueryError` (and subclasses like `GenerationError`) mid-stream and yields `<!-- error: <message> -->` sentinel so HTMX clients render a "stream interrupted" indicator instead of a truncated response. Audit H6 closed. 5 new `SafeStreamTests`; 225 tests pass.
- **3.3**: Extracted `documents.services.pipeline.ingest_uploaded_pdf(upload, *, username=None) -> Document` — the canonical "user uploaded a PDF" entry point. Owns temp-file lifecycle, `Document.objects.create`, cleanup on failure. `username` is keyword-only; path-traversal protection via `PurePath(upload.name).name`. Both upload views delegate to it. 6 new `IngestUploadedPdfTests`; 238 tests pass.
- **3.4**: Extracted `documents.views._uploads._process_uploads(uploads, *, username) -> (results, status_code)`. The two upload views shrink to 4-line adapters. Status-code logic preserved verbatim (any success → 201, all-validation → 400, all-failure → 500). `documents/views.py` became a `documents/views/` package with `__init__.py` re-exporting everything. 6 new `ProcessUploadsTests`; 244 tests pass.
- **3.5**: Verification — `pytest policyiq/` → **250 passed**; `ruff check policyiq/` clean; `ruff format --check policyiq/` clean (76 files); `pre-commit run --all-files` clean (10 hooks); `python manage.py check` → 0 issues. **Audit impact**: closes L11 (upload-loop dedup), L13 (mid-stream error surfacing), and creates the service-layer split that M9/M10/M12 (Phase 4) build on.

## Next — Phase 4
Test coverage batch: the audit-M findings that require explicit test coverage — H7, H8, M7, M9, M10, M11, M12, M14, L1, L8, L11, L13. The service-layer split from Phase 3 is the precondition.
