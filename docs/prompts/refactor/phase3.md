<!--
This file is one slice of the 6-phase refactor described in docs/prompts/refactor_prompt.md.
Commit format: <type>(<scope>): <summary> [PhaseN.X]. Read the prompt's Git Setup, TDD Rules, and Locked Decisions sections before starting.
-->

# Phase 3 — View → service consolidation (audit H5, M2, M3, L11)

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
2. **Implement** `run_query` to call `retrieve_chunks`, then `build_prompt` (which already returns `None` for "no information"), then `generate_response`. Wrap the streaming in a small adapter ([see §3.2](#32-wrap-generate_response-to-surface-mid-stream-errors-audit-h6)).
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
