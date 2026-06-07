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
