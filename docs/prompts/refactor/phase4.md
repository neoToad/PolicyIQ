<!--
This file is one slice of the 6-phase refactor described in docs/prompts/refactor_prompt.md.
Commit format: <type>(<scope>): <summary> [PhaseN.X]. Read the prompt's Git Setup, TDD Rules, and Locked Decisions sections before starting.
-->

# Phase 4 — Test coverage (audit H7, H8, M7, M9, M10, M11, M12, M14, L1, L8, L11, L13)

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

After Phase 2.2's decision (Locked Decision #1: drop `DocumentDeleteView`, staff-only), write tests in `policyiq/documents/tests/test_views.py`:
- `test_staff_can_delete`.
- `test_non_staff_gets_403`.
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
- **L13** `test_views_pytest.py` consolidation: **Per Locked Decision #4 in `../refactor_prompt.md`, keep `test_views_pytest.py` and delete `test_views.py`.** The `conftest.py` fixtures stay. Commit: `chore(queries): drop duplicate Django TestCase view tests`.
- **L11** `_process_uploads` extraction: if not already done in Phase 3.4, do it here.
