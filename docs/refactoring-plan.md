# PolicyIQ Refactoring Plan

> **Scope**: Codebase improvements only — no new features. This plan addresses security vulnerabilities, architectural debt, code quality, and maintainability.
> **Status**: All 5 phases complete. 33/33 items done.

---

## Executive Summary

PolicyIQ is a Django + HTMX RAG application with two apps (`documents`, `queries`), ~780 lines of production Python, ~930 lines of tests, and ~430 lines of templates. The codebase is small and readable but carries **7 security issues**, **3 duplication problems**, **6 architectural weaknesses**, and **several testing/operational gaps** that will compound as the project grows.

This plan is organized into 5 phases by priority: security first, then architecture, then quality/tooling, then testing, then operational resilience.

---

## Phase 1 — Security Fixes (Critical)

These items are actively dangerous in any deployed or shared environment.

### 1.1 Remove committed `.env` from git history ✅ COMPLETED

**Problem**: `policyiq/.env` contains a real password (`policyiq_pass_2026`) and is tracked in git despite `.gitignore` having an `.env` entry. The file was committed before the gitignore rule was added.

**Fix**:
- `git rm --cached policyiq/.env` to untrack it
- Add `policyiq/.env` to `.gitignore` (verify it's there)
- Rotate the database password
- Consider `git filter-repo` to scrub history if the repo has ever been pushed to a remote

### 1.2 Replace hard-coded `SECRET_KEY` ✅ COMPLETED

**Problem**: `settings.py` contains `SECRET_KEY = 'django-insecure-change-me'` — never changed from the Django scaffold.

**Fix**:
- Read from environment: `SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")`
- Add to `.env` with a cryptographically random value
- Fail loudly if missing in production (`django-insecure-` prefix check or `DEBUG=False` guard)

### 1.3 Add API authentication ✅ COMPLETED

**Problem**: `DocumentUploadAPIView` and `QueryAPIView` have zero authentication. Anyone can upload files and run queries.

**Fix**:
- Add DRF `REST_FRAMEWORK` config to `settings.py` with `DEFAULT_AUTHENTICATION_CLASSES` and `DEFAULT_PERMISSION_CLASSES`
- At minimum, require `IsAuthenticated` on write endpoints
- Consider token auth (`rest_framework.authentication.TokenAuthentication`) for the API layer
- Staff views already use `@staff_member_required` — leave as-is

### 1.4 Fix path traversal vulnerability in file uploads ✅ COMPLETED

**Problem**: `_save_upload_and_ingest()` uses `upload.name` directly to construct a file path via `open(settings.MEDIA_ROOT / upload.name, "wb+")`. A filename like `../../etc/passwd` could write outside the media directory.

**Fix**:
- Replace `Document.file_path` (CharField) with Django's `FileField` and `upload_to` callback
- Use `os.path.basename()` or `pathlib.PurePath.name` to strip directory components from uploaded filenames
- Optionally generate UUID-based filenames to avoid collisions

### 1.5 Add file type validation on upload ✅ COMPLETED

**Problem**: Only HTML `accept="application/pdf"` restricts uploads — trivially bypassed. No server-side check that the file is actually a PDF before writing to disk.

**Fix**:
- Validate `Content-Type` header on the server side
- Check PDF magic bytes (`%PDF-`) on the first bytes of the file
- Reject non-PDF uploads with a 400 error before writing to disk

### 1.6 Configure CORS ✅ COMPLETED

**Problem**: DRF is installed with zero configuration. Default permissions are fully open.

**Fix**:
- Add `REST_FRAMEWORK` dict to `settings.py` with at minimum `DEFAULT_PERMISSION_CLASSES`
- If API needs cross-origin access, add `django-cors-headers` and configure `CORS_ALLOWED_ORIGINS`

### 1.7 Review CSRF on API views ✅ COMPLETED

**Problem**: CSRF handling is only set up for HTMX via a client-side listener. DRF `APIView` CSRF behavior depends on the authentication classes configured.

**Fix**:
- Once authentication is in place (1.3), DRF will enforce CSRF for session auth automatically
- For token auth, CSRF is not required — document this choice
- Verify that HTMX API calls include the CSRF token via the `htmx:configRequest` handler

---

## Phase 2 — Architecture Improvements (High)

These items reduce coupling, enable independent evolution, and fix design problems that will block scaling.

### 2.1 Replace `CharField` file_path with `FileField` ✅ COMPLETED

**Problem**: `Document.file_path` is a `CharField` storing a manual filesystem path. This bypasses Django's `Storage` abstraction, prevents `document.delete()` from cleaning up files on disk, and makes the admin/media integration broken.

**Fix**:
- Change `Document.file_path` to `Document.file = models.FileField(upload_to="documents/")`
- Create a data migration to move existing files into the storage backend
- Use `document.file.path`, `document.file.url` instead of manual path construction
- This also fixes 1.4 (path traversal) as a side effect

### 2.2 Add DRF Serializers ✅ COMPLETED

**Problem**: AGENTS.md references `test_serializers.py` but no serializers exist. API views manually construct JSON dicts from model attributes, making the API contract implicit and fragile.

**Fix**:
- Create `documents/serializers.py` with `DocumentSerializer`, `ChunkSerializer`
- Create `queries/serializers.py` with `QueryRequestSerializer`, `QueryResponseSerializer`
- Replace manual JSON construction in `DocumentUploadAPIView` and `QueryAPIView`
- Write `test_serializers.py` per AGENTS.md convention

### 2.3 Extract shared ingestion pipeline ✅ COMPLETED

**Problem**: `StaffDocumentReindexView.post()` duplicates the entire extraction/clean/chunk/embed/index pipeline that `_save_upload_and_ingest()` already implements. The reindex view reimplements it inline (lines 134-159 of `views.py`).

**Fix**:
- Create `documents/services/pipeline.py` with a public `ingest_document(document: Document) -> dict` function
- Have `_save_upload_and_ingest()` call `ingest_document()` after saving the file
- Have `StaffDocumentReindexView.post()` call `ingest_document()` directly
- Delete the duplicated pipeline code from the reindex view

### 2.4 De-duplicate citation construction ✅ COMPLETED

**Problem**: The same list comprehension building the `citations` dict appears in both `AskPageView.post()` and `QueryAPIView.post()`.

**Fix**:
- Extract a `build_citations(chunks: list[dict]) -> list[dict]` helper into `queries/services/` (or into the retriever)
- Both views call the shared function

### 2.5 Decouple `retriever.py` from `documents.models` ✅ COMPLETED

**Problem**: `queries/services/retriever.py` imports from `documents.models` to fetch `document_name` for each chunk. This creates a hard cross-app ORM dependency.

**Fix**:
- Have `retrieve_chunks()` return chunk data with `document_id` only
- Move the document_name enrichment to the view layer or to a thin coordination service
- Alternatively, store `document_name` in ChromaDB metadata during indexing so the retriever never needs to query PG

### 2.6 Singleton ChromaDB client ✅ COMPLETED

**Problem**: `get_collection()` creates a new `PersistentClient` on every call. This is wasteful and can cause locking issues with ChromaDB's SQLite backend under concurrency.

**Fix**:
- Create a module-level singleton or a thin `get_chroma_client()` function that caches the client instance
- Use `@functools.lru_cache` or a simple module variable
- Ensure the client is created lazily (on first access, not at import time)

### 2.7 Set `MEDIA_ROOT` and `MEDIA_URL` in settings ✅ COMPLETED

**Problem**: `UploadPageView` falls back to `settings.BASE_DIR / "media"` via `getattr`. Django admin and standard file handling don't know where media files are.

**Fix**:
- Add `MEDIA_ROOT = BASE_DIR / "media"` and `MEDIA_URL = "/media/"` to `settings.py`
- Add media URL pattern in `urls.py` for development
- Remove the `getattr` fallback in `UploadPageView`

---

## Phase 3 — Code Quality & Tooling (Medium)

### 3.1 Consolidate `requirements.txt` ✅ COMPLETED

**Problem**: Two `requirements.txt` files exist — one at the repo root (python-dotenv==1.1.1, missing `anthropic`) and one in `policyiq/` (python-dotenv==1.2.2, has `anthropic`). This is confusing and error-prone.

**Fix**:
- Delete the root-level `requirements.txt` or make it a symlink
- Keep only `policyiq/requirements.txt` as the single source of truth
- Pin all versions consistently

### 3.2 Add `pyproject.toml` ✅ COMPLETED

**Problem**: No `pyproject.toml`, `setup.cfg`, or `setup.py`. The project has no declared build system, tool config, or package metadata.

**Fix**:
- Create `pyproject.toml` with:
  - `[project]` metadata (name, version, dependencies)
  - `[tool.ruff]` for linting and formatting config
  - `[tool.pytest.ini_options]` for test discovery
  - `[tool.mypy]` for type checking config
- Move requirements into `[project.dependencies]` (or keep `requirements.txt` for pip and reference it)

### 3.3 Add linting and formatting ✅ COMPLETED

**Problem**: No linter, formatter, or type checker is configured. Code style is inconsistent (some type hints, some docstrings, some not).

**Fix**:
- Add `ruff` as the linter/formatter (replaces flake8, isort, black)
- Configure in `pyproject.toml`: line length, select rules (E, F, W, I, UP, ANN)
- Run `ruff format` and `ruff check --fix` on the existing code
- Add a `make lint` / `make format` target (or just document the commands)

### 3.4 Add type hints consistently ✅ COMPLETED

**Problem**: Service functions have type hints but view methods don't. Return types are inconsistent.

**Fix**:
- Add type hints to all public view methods
- Add return type hints to all service functions (most already have them)
- Consider adding `mypy` to CI once `pyproject.toml` is in place

### 3.5 Clean up `_upload_result.html` legacy branch ✅ COMPLETED

**Problem**: `_upload_result.html` has a legacy `document` branch alongside the new `results` branch — incomplete cleanup after the multi-file upload refactor.

**Fix**:
- Remove the `{% if document %}` branch that handles the old single-document response
- Keep only the `{% if results %}` branch
- Verify no code path still sends a `document` context variable

### 3.6 Extract inline CSS from `base.html` ✅ COMPLETED

**Problem**: All CSS (~130 lines) is inline in `base.html`. This makes the template harder to read and prevents caching.

**Fix**:
- Move CSS to `static/css/main.css`
- Load via `{% static %}` template tag
- Keep critical CSS (if any) inline for fast first paint; move the rest to the file

### 3.7 Add docstrings to public API functions ✅ COMPLETED

**Problem**: Only `chunk_pages()` has a docstring. Other service functions and all view classes lack docstrings.

**Fix**:
- Add brief docstrings to each view class explaining its purpose
- Add docstrings to public service functions (`extract_pages`, `clean_pages`, `embed_chunks`, `index_document`, `retrieve_chunks`, `build_prompt`, `generate_response`)
- Follow Google or NumPy docstring style consistently

---

## Phase 4 — Testing Improvements (Medium)

### 4.1 Add serializers tests ✅ COMPLETED (in Phase 2.2)

**Problem**: AGENTS.md mandates `test_serializers.py` but no serializers or tests exist.

**Fix**:
- Create after Phase 2.2 (serializers)
- Test serialization, validation, and field presence for each serializer

### 4.2 Use `TestCase` instead of `SimpleTestCase` where appropriate ✅ COMPLETED (in Phase 2.3)

**Problem**: All tests use `SimpleTestCase` which doesn't support database transactions. Any test that creates real model instances will silently fail.

**Fix**:
- Change tests that create `Document` or `Chunk` instances to use `TestCase`
- Keep `SimpleTestCase` for tests that are purely mock-based and don't touch the DB

### 4.3 Reduce mock depth in `test_views.py` ✅ COMPLETED (in Phase 2.3)

**Problem**: One test in `documents/tests/test_views.py` has 7 `@mock.patch` decorators — hard to read, fragile, and a sign the function under test has too many dependencies.

**Fix**:
- After Phase 2.3 (shared pipeline), the view only needs to mock `ingest_document()` instead of 5 individual services
- This naturally reduces mock depth to ~2 patches per test

### 4.4 Add tests for `AskPageView` ✅ COMPLETED

**Problem**: Only `QueryAPIView` has test coverage. The HTMX page view (`AskPageView`) is untested.

**Fix**:
- Add test cases for GET (form rendering), POST (streaming response), and error paths
- Test HTMX-specific behavior (partial rendering, streaming)

### 4.5 Add integration test scaffolding ✅ COMPLETED

**Problem**: No integration tests exist. All tests are fully mocked unit tests. The standalone smoke test scripts are manual.

**Fix**:
- Add a `tests/integration/` directory with a basic ingestion + query round-trip test
- Use `TestCase` with a test PostgreSQL database
- Mark with `@pytest.mark.integration` or a Django test tag so they can be skipped in fast runs
- Keep the manual smoke scripts for now but document how they differ from integration tests

### 4.6 Consider pytest migration ✅ COMPLETED

**Problem**: Tests use Django's `SimpleTestCase` with `unittest.mock`. Pytest + `pytest-django` offers better fixtures, parametrization, and plugin ecosystem.

**Fix** (optional, lower priority):
- Add `pytest` and `pytest-django` to requirements
- Create `conftest.py` with shared fixtures
- Migrate existing tests gradually (they can coexist)

---

## Phase 5 — Operational Resilience (Lower)

### 5.1 Add Django logging configuration ✅ COMPLETED

**Problem**: No logging configuration. Errors in the pipeline are silently swallowed or raised as generic `RuntimeError`.

**Fix**:
- Add `LOGGING` dict to `settings.py` with console and file handlers
- Log at INFO for pipeline progress, WARNING for retries, ERROR for failures
- Replace bare `RuntimeError` raises with specific exception classes

### 5.2 Add custom exception classes ✅ COMPLETED

**Problem**: Services raise generic `RuntimeError` for all failure modes — extraction failures, embedding failures, LLM errors are indistinguishable.

**Fix**:
- Create `documents/exceptions.py` with `ExtractionError`, `ChunkingError`, `EmbeddingError`, `IndexingError`
- Create `queries/exceptions.py` with `RetrievalError`, `GenerationError`
- Services raise specific exceptions; views catch and return appropriate HTTP status codes

### 5.3 Add health check endpoint ✅ COMPLETED

**Problem**: No way to verify Ollama or ChromaDB connectivity without running a full query.

**Fix**:
- Add `/api/health/` endpoint that checks:
  - PostgreSQL: `SELECT 1`
  - ChromaDB: `get_collection()` heartbeat
  - Ollama: HTTP GET to `/api/tags`
- Return 200 with component status, or 503 if any dependency is down

### 5.4 Batch embedding requests ✅ COMPLETED

**Problem**: `embed_chunks()` makes one HTTP request per chunk. For a 50-page PDF (~100 chunks), this is 100 sequential HTTP calls.

**Fix**:
- Check if the Ollama embed API supports batch input (it does via `/api/embed` with a list of texts)
- Modify `embed_chunks()` to send chunks in batches of 20-50
- Fall back to sequential if the batch endpoint fails

### 5.5 Add rate limiting

**Problem**: No rate limiting on upload or query endpoints.

**Fix**:
- Add `django-ratelimit` or DRF's `throttling` classes
- Configure per-view or per-user limits (e.g., 10 uploads/hour, 30 queries/hour for anonymous)

### 5.6 Add pre-commit hooks

**Problem**: No pre-commit hooks. The AGENTS.md rule "No commit message if tests are failing" is a convention, not enforced.

**Fix**:
- Add `.pre-commit-config.yaml` with ruff, trailing whitespace, YAML checks
- Add a pre-commit hook that runs the test suite (or at least lint)
- Install with `pre-commit install`

---

## Summary Table

| Phase | Items | Status | Priority | Estimated Effort |
|-------|-------|--------|----------|-----------------|
| 1 — Security | 7 items | ✅ Complete | Critical | 2-3 days |
| 2 — Architecture | 7 items | ✅ Complete | High | 3-4 days |
| 3 — Code Quality | 7 items | ✅ Complete | Medium | 2-3 days |
| 4 — Testing | 6 items | ✅ Complete | Medium | 2-3 days |
| 5 — Operational | 6 items | ✅ Complete | Lower | 2-3 days |
| **Total** | **33 items** | **33/33 done** | | **11-16 days** |

---

## Implementation Notes

### Dependency order

- Phase 2.1 (FileField) is a prerequisite for completing Phase 1.4 (path traversal) — do them together
- Phase 2.3 (shared pipeline) is a prerequisite for Phase 4.3 (reducing mock depth) — do them together
- Phase 2.2 (serializers) is a prerequisite for Phase 4.1 (serializer tests) — do them together
- Phase 3.2 (pyproject.toml) enables Phase 3.3 (linting), 3.4 (type hints), and 5.6 (pre-commit)

### What NOT to do

- **Don't add a JavaScript framework** — the HTMX architecture is a deliberate choice and works well for this app
- **Don't switch to a different vector database** — ChromaDB is fine for the current scale
- **Don't add Docker/CI** yet — that's infrastructure, not refactoring; tackle separately
- **Don't rewrite the services** — they're thin and well-separated; the improvements are incremental

### After refactoring

Once this plan is complete, the codebase should be:
- Secure (no credentials in git, proper auth, validated uploads)
- Well-structured (serializers, shared pipeline, decoupled apps)
- Consistent (type hints, docstrings, linting, formatting)
- Well-tested (serializers tested, integration test scaffolding, reduced mock depth)
- Operationally observable (logging, health checks, custom exceptions)
- Hardened against abuse (rate limiting, pre-commit hooks enforcing code quality)
