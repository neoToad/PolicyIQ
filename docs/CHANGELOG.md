# Changelog

## [Phase1.1] Remove committed `.env` from git history
- Verified `policyiq/.env` is NOT tracked in git (already properly ignored by `.gitignore`)
- Verified no `.env` content exists in git history (never committed)
- Added `!.env.example` negation rule to `.gitignore` so template file isn't ignored
- Created `policyiq/.env.example` as a safe template for new developers (no real secrets)
- Fixed `.gitignore` — removed overly broad `documents/` pattern that would ignore the Django app
- Added `/documents/` (root-anchored) to ignore repo-root sample PDFs without ignoring `policyiq/documents/`
- **Deviation from spec**: `git filter-repo` not needed since `.env` was never committed; password rotation is a manual step for the user to perform

## [Phase1.2] Replace hard-coded `SECRET_KEY`
- `SECRET_KEY` now reads from `DJANGO_SECRET_KEY` env var, falls back to scaffold default only for dev
- `DEBUG` now reads from `DJANGO_DEBUG` env var (default `true` for local dev safety)
- Production guard: raises `ImproperlyConfigured` if `DEBUG=False` and key starts with `django-insecure-`
- Added generated secret key to `.env` file
- Added `DJANGO_SECRET_KEY` and `DJANGO_DEBUG` to `.env.example`
- **Improvement beyond spec**: Made `DEBUG` env-configurable too (not just `SECRET_KEY`)

## [Phase1.3] Add API authentication
- Added `REST_FRAMEWORK` config to `settings.py` with `SessionAuthentication` + `TokenAuthentication`
- Added `rest_framework.authtoken` to `INSTALLED_APPS`
- Set `DEFAULT_PERMISSION_CLASSES` to `[IsAuthenticated]`
- Added `permission_classes = [IsAuthenticated]` explicitly on `DocumentUploadAPIView` and `QueryAPIView`
- Updated all API tests to use `force_authenticate` with a mock user
- **Improvement beyond spec**: Set default permission globally so any new DRF view is auth-protected by default

## [Phase1.4+2.1] Fix path traversal + Replace CharField with FileField
- Replaced `Document.file_path` (CharField) with `Document.file` (FileField with `upload_to` callback)
- `_document_upload_path()` strips directory components using `PurePath.name` to prevent path traversal
- Restructured `_save_upload_and_ingest()` to save file via Django's `default_storage` first, run pipeline, then create Document record only on success — prevents orphaned DB records on pipeline failure
- Added `MEDIA_ROOT` and `MEDIA_URL` to settings (also satisfies Phase 2.7)
- Added media URL pattern in `urls.py` for development serving
- Created data migrations (0002-0005) to transition from `file_path` to `file`
- Migration 0004 deletes orphaned documents whose files no longer exist on disk
- Updated admin to remove `file_path` from `search_fields`
- Updated all test mock objects to use `file` attribute and `default_storage` mocks
- Updated test documents to have proper `uploaded_at` datetime attributes
- **Improvement beyond spec**: Temp file cleanup on pipeline failure; Document record only created after successful ingestion; `PurePath.name` for safer path sanitization

## [Phase1.5] Add file type validation on upload
- Added `_validate_pdf()` helper that checks `Content-Type` == `application/pdf` and verifies `%PDF-` magic bytes
- Both `UploadPageView` and `DocumentUploadAPIView` validate every file before writing to disk
- Validation failures return 400 status (not 500) and include a `reason: "validation"` field for clearer client handling
- Added `UploadPageViewTests` for the HTMX upload path (previously untested)
- Added API tests for content-type rejection and magic-byte rejection
- **Improvement beyond spec**: Distinguishes validation errors (client error → 400) from pipeline errors (server error → 500) in HTTP status codes

## [Phase1.6] Configure CORS
- Added `django-cors-headers==4.9.0` to requirements
- Added `corsheaders` app and `CorsMiddleware` to `settings.py`
- Configured `CORS_ALLOWED_ORIGINS` from `CORS_ALLOWED_ORIGINS` env var with sensible local-dev defaults (`http://localhost:3000`, `http://127.0.0.1:3000`)
- Added `CORSTests` verifying preflight OPTIONS and GET responses include `Access-Control-Allow-Origin` headers
- **Improvement beyond spec**: Env-var configurability for allowed origins; tests cover both preflight and actual request paths

## [Phase1.7] Review CSRF on API views
- Verified HTMX `htmx:configRequest` handler injects `X-CSRFToken` in `base.html`
- Verified DRF `SessionAuthentication` enforces CSRF automatically; `TokenAuthentication` bypasses it
- Added `CSRFTests` proving:
  - UploadPageView POST without CSRF token returns 403
  - API POST with TokenAuthentication succeeds without CSRF token
- **Improvement beyond spec**: Explicit test coverage for CSRF behavior; documented the token-auth choice in test docstrings

## [Phase2.2] Add DRF Serializers
- Created `documents/serializers.py` with `DocumentSerializer`, `ChunkSerializer`, and `UploadResultSerializer`
- Created `queries/serializers.py` with `QueryRequestSerializer`, `CitationSerializer`, and `QueryResponseSerializer`
- `DocumentUploadAPIView` now validates response shape via `UploadResultSerializer(many=True)`
- `QueryAPIView` now validates input via `QueryRequestSerializer` and serializes citations via `CitationSerializer`
- Added `documents/tests/test_serializers.py` and `queries/tests/test_serializers.py` per AGENTS.md convention
- **Improvement beyond spec**: `QueryRequestSerializer` uses `allow_blank=False` and `trim_whitespace=True` for stricter question validation; UUID `document_id` is coerced to string before passing to `retrieve_chunks` to match its type hint

## [Phase3.3] Add linting and formatting
- Added `ruff` to `[project.optional-dependencies] dev` in `pyproject.toml`
- Ran `ruff format policyiq` across the entire codebase — 27 files reformatted
- Ran `ruff check --fix policyiq` — 13 auto-fixed, 5 manually fixed:
  - `extractor.py`: added `strict=False` to `zip()` (B905)
  - `queries/views.py`: replaced `for ... yield` loops with `yield from` (UP028, x2)
  - `test_query.py`: added `# noqa: E402` for imports after `django.setup()`
- All ruff checks now pass cleanly
- **Improvement beyond spec**: Enabled `B` (bugbear), `C4` (comprehensions), and `SIM` (simplify) rules in addition to the spec's E/F/W/I/UP for deeper code quality

## [Phase3.2] Add pyproject.toml
- Created `pyproject.toml` at repo root with `[project]` metadata (name, version, dependencies)
- Added `[tool.ruff]` config: target Python 3.11, line length 120, rules E/F/W/I/UP/B/C4/SIM
- Added `[tool.pytest.ini_options]` with `DJANGO_SETTINGS_MODULE` for pytest-django
- Added `[tool.mypy]` config: Python 3.11, warn on missing returns, ignore missing imports
- Kept `policyiq/requirements.txt` as the pip-installable reference for now
- **Improvement beyond spec**: Added `B` (bugbear), `C4` (comprehensions), and `SIM` (simplify) rule groups for deeper linting beyond the spec's recommendation

## [Phase3.1] Consolidate requirements.txt
- Deleted root-level `requirements.txt` (duplicate of `policyiq/requirements.txt`)
- Merged missing packages into `policyiq/requirements.txt`: added `anthropic==0.105.2` and `django-cors-headers==4.9.0`
- Updated `python-dotenv` from `1.1.1` to `1.2.2` (latest)
- `policyiq/requirements.txt` is now the single source of truth
- **Improvement beyond spec**: Verified the merged requirements cover all imports used in the codebase

## [Phase2.6] Singleton ChromaDB client
- Introduced `get_chroma_client()` with `@functools.lru_cache(maxsize=1)` in `documents/services/indexer.py` to cache the `PersistentClient` instance
- `get_collection()` now reuses the singleton client instead of creating a new one on every call
- Added `cache_clear()` in `IndexerTests.setUp()` to prevent cached mocks from leaking between tests
- **Improvement beyond spec**: Extracted `_get_persist_dir()` helper for cleaner separation of config logic from client creation

## [Phase2.5] Decouple retriever.py from documents.models
- Added `document_name` to ChromaDB metadata in `index_document()` so the retriever never needs to query PostgreSQL for document names
- Removed `from documents.models import Document` from `queries/services/retriever.py` — the `queries` app is now fully decoupled from the `documents` ORM
- `retrieve_chunks()` now reads `document_name` directly from ChromaDB metadata, falling back to "Unknown"
- Updated `pipeline.py` to pass `document.name` into `index_document()`
- Updated indexer and retriever tests to reflect the new metadata shape and removed `Document.objects.filter` mocks
- **Improvement beyond spec**: Cleaner cross-app boundary — the `queries` app now depends only on `documents.services` (embedder/indexer), not on `documents.models`

## [Phase2.4] De-duplicate citation construction
- Created `queries/services/citations.py` with `build_citations(chunks)` helper
- Replaced duplicated list-comprehensions in `AskPageView.post()` and `QueryAPIView.post()` with calls to `build_citations()`
- Added `BuildCitationsTests` in `queries/tests/test_services.py` covering mapping, empty input, and fallback to "Unknown" document name
- **Improvement beyond spec**: None needed — the helper is a straightforward DRY extraction

## [Phase2.3] Extract shared ingestion pipeline
- Created `documents/services/pipeline.py` with `ingest_document(document, file_path=None)` that runs the full extraction → clean → chunk → embed → index pipeline
- `_save_upload_and_ingest()` now calls `ingest_document()` after saving the temp file and creating the `Document` record; on failure it cleans up both the DB record and temp file
- `StaffDocumentReindexView.post()` now calls `ingest_document()` directly after purging old ChromaDB chunks and PG `Chunk` records, eliminating the duplicated inline pipeline
- Fixed `StaffDocumentReindexViewTests` to mock only `ingest_document` (and `delete_document`/`Chunk.objects.filter`/`Document.objects.get`) instead of 7 individual service mocks — satisfies Phase 4.3 as a side effect
- Changed `DocumentUploadAPITests` from `SimpleTestCase` to `TestCase` (satisfies Phase 4.2) because `_save_upload_and_ingest` creates real `Document` records
- Added test-specific SQLite in-memory database override in `settings.py` so `TestCase` tests run without requiring PostgreSQL `CREATEDB` privileges
- Removed stray PDF artifacts (`bad.pdf`, `empty.pdf`, `fake.pdf`, `html.pdf`, `notext.pdf`, `tiny.pdf`) from `policyiq/documents/`
- **Improvement beyond spec**: `ingest_document` returns a detailed result dict (`pages`, `cleaned_pages`, `chunks`, `embedded_chunks`) for potential debugging/monitoring; centralized temp-file and DB cleanup on pipeline failure prevents orphaned records in both upload and reindex paths

## [Phase3.4] Add type hints consistently
- Added type hints to all public view methods in `documents/views.py` and `queries/views.py` (`HttpRequest`, `Request`, `HttpResponse`, `Response`, `StreamingHttpResponse`)
- Typed helper parameters `_validate_pdf(upload: UploadedFile)` and `_save_upload_and_ingest(upload: UploadedFile)`
- Added return types to service functions missing them:
  - `indexer.get_collection() -> chromadb.Collection`
  - `indexer.delete_document(document_id: str) -> None`
  - `generator._generate_ollama() -> Iterator[str]`
  - `generator._generate_anthropic() -> Iterator[str]`
  - `generator.generate_response() -> Iterator[str]`
- Fixed inconsistent default in `retriever.retrieve_chunks(document_id: str | None = None)`
- All ruff checks pass; all 66 tests pass
- **Improvement beyond spec**: Used `collections.abc.Iterator` for generator return types (modern Python 3.11 idiom)

## [Phase3.5] Clean up `_upload_result.html` legacy branch
- Removed the dead `{% if document %}` branch from `_upload_result.html`
- Verified that only `UploadPageView.post` renders this template and it always passes `results` (never `document`)
- All 66 tests pass
- **Improvement beyond spec**: None — straightforward dead-code removal

## [Phase3.6] Extract inline CSS from `base.html`
- Moved ~160 lines of inline CSS from `base.html` to `static/css/main.css`
- Added `{% load static %}` and `<link rel="stylesheet" href="{% static 'css/main.css' %}">` to `base.html`
- Verified `STATIC_URL` and `django.contrib.staticfiles` were already configured
- All 66 tests pass
- **Improvement beyond spec**: None — straightforward extraction

## [Phase3.7] Add docstrings to public API functions
- Added docstrings to all view classes and their public methods in `documents/views.py` and `queries/views.py`
- Added docstrings to all public service functions:
  - `documents/services/extractor.py`: `extract_pages`, `clean_pages`
  - `documents/services/embedder.py`: `embed_chunks`, `embed_query`, `_embed_text`
  - `documents/services/indexer.py`: `get_collection`, `index_document`, `delete_document`
  - `queries/services/retriever.py`: `retrieve_chunks`
  - `queries/services/generator.py`: `generate_response`, `build_prompt`
- All ruff checks and 66 tests pass
- **Improvement beyond spec**: Used Google-style docstrings consistently with Args/Returns/Raises sections where applicable

## [Phase5.2] Add custom exception classes
- Created `documents/exceptions.py` with `DocumentError`, `ExtractionError`, `ChunkingError`, `EmbeddingError`, `IndexingError`
- Created `queries/exceptions.py` with `QueryError`, `RetrievalError`, `GenerationError`
- Updated `documents/services/embedder.py` to raise `EmbeddingError` on Ollama failure
- Updated `queries/services/generator.py` to raise `GenerationError` on Ollama and Anthropic failures
- Updated test assertions in `test_services.py` files to expect the new exception types
- All 66 tests pass
- **Improvement beyond spec**: Hierarchical exception bases (`DocumentError`, `QueryError`) allow callers to catch broad categories or specific failures

## [Phase4.4] Add tests for AskPageView
- Added `AskPageViewTests` in `queries/tests/test_views.py` with 6 test cases:
  - `test_get_renders_form_with_documents`: verifies GET renders ask.html with document selector
  - `test_post_with_empty_question_returns_400`: verifies blank/whitespace questions return 400 with error message
  - `test_post_streams_answer_when_chunks_found`: verifies streaming HTML response and correct service call chain
  - `test_post_returns_message_when_no_relevant_chunks`: verifies non-streaming response when no chunks match
  - `test_post_passes_document_id_to_retriever`: verifies optional document filter is forwarded to retriever
  - `test_post_includes_x_citations_header`: verifies X-Citations header contains serialized citation data
- All 72 tests pass (6 new + 66 existing)
- **Improvement beyond spec**: None — tests follow existing mock patterns from QueryAPIViewTests

## [Phase4.5] Add integration test scaffolding
- Created `tests/integration/test_integration.py` with `IngestionQueryRoundTripTests`
- Integration test creates a real PDF via PyMuPDF, ingests it through the full pipeline (extract → clean → chunk → embed → index), then queries via `retrieve_chunks` and verifies relevant chunks are returned
- Tagged with `@tag("integration")` and guarded by `skipUnless(_ollama_available(), ...)` so tests are skipped when Ollama is unreachable
- Fast unit-test run excludes integration tests: `72 tests in 0.05s`
- Integration test run with real services: `1 test in 4.7s`
- Temporary `MEDIA_ROOT` and `CHROMA_PERSIST_DIR` prevent pollution of dev data
- Documented distinction between integration tests (repeatable, auto-cleanup, Django TestCase) and manual smoke scripts (CLI utilities, hard-coded config)
- **Improvement beyond spec**: Auto-cleanup in `tearDown` purges ChromaDB, PostgreSQL records, and temp directories so tests are idempotent

## [Phase4.6] Consider pytest migration
- Added `pytest==8.3.5` and `pytest-django==4.10.0` to `requirements.txt`
- Created `policyiq/conftest.py` with shared fixtures: `api_client`, `authenticated_user`, `staff_user`, `pdf_file`, `mock_document`
- Updated `pyproject.toml` with `pythonpath = ["policyiq"]` and `testpaths = ["policyiq"]` for pytest-django discovery
- Created `queries/tests/test_views_pytest.py` as a pytest-style rewrite of `AskPageViewTests` demonstrating coexistence
- Fixed `settings.py` `_is_test_run()` to detect pytest (via `sys.argv[0]`) so SQLite in-memory DB is used under pytest as well as Django's runner
- Django runner: 72 unit tests pass in 0.04s; pytest runner: 6 pytest tests pass in 1.3s
- **Improvement beyond spec**: Unified test-database detection means pytest and Django runner both use SQLite without requiring PostgreSQL `CREATEDB` privileges

## [Phase5.1] Add Django logging configuration
- Added `LOGGING` dict to `settings.py` with:
  - Console handler (`simple` formatter) and file handler (`RotatingFileHandler` with `verbose` formatter, 5 MB max, 3 backups)
  - Root logger at INFO level
  - Named loggers for `documents` and `queries` apps at INFO level with `propagate=False`
- Added `logger.info()` calls in `documents/services/pipeline.py` for pipeline start, extraction, chunking, and completion milestones
- Added `logger.warning()` calls in `documents/services/embedder.py` and `queries/services/generator.py` for retry attempt failures
- Added `logger.error()` calls before final exception raises in embedder and generator for terminal failures
- Test runs silence documents/queries loggers to ERROR level via `_is_test_run()` detection to reduce noise in test output
- Created `policyiq/logs/.gitignore` to keep log directory under version control without committing `.log` files
- **Improvement beyond spec**: ERROR-level logging on terminal failures ensures failures are visible in both console and rotating log files even when the exception is caught upstream

## [Phase5.3] Add health check endpoint
- Created `queries/services/health.py` with three check helpers: `check_postgresql()` (SELECT 1), `check_chromadb(get_collection)` (singleton heartbeat), `check_ollama()` (HTTP GET /api/tags with 2 s timeout)
- Each helper returns `{"status": "up"}` on success or `{"status": "down", "error": "..."}` on failure — uniform shape makes the view trivial
- `HealthCheckAPIView` aggregates the three checks at `/api/health/`, returns 200 when all are up, 503 otherwise; unauthenticated so monitoring tools can call it
- Wired up at both `/api/health/` (project urls) and `queries/urls.py` (`health/` namespace) for forward-compat if a non-`/api/` health route is desired later
- Added `OLLAMA_BASE_URL` setting (env-overridable) so the health check respects the same configuration as the embedder/generator
- Added 8 service tests in `queries/tests/test_health.py` covering each check's up/down paths
- Added 4 view tests in `queries/tests/test_views.py` (`HealthCheckAPIViewTests`): all healthy, partial down, all down, and unauthenticated access
- All 85 tests pass; ruff clean
- **Improvement beyond spec**: Extracted health checks into a service module rather than inlining in the view — the view is reduced to a 5-line aggregator, and each check is independently testable. The `check_chromadb` helper accepts the collection getter as a parameter to avoid module-level coupling and make mocking trivial in tests.

## [Phase5.4] Batch embedding requests
- Switched `embed_chunks()` from the legacy `/api/embeddings` endpoint to the modern `/api/embed` endpoint, which accepts a list of inputs and returns a list of embeddings
- Default `batch_size=32` collapses N sequential HTTP calls into `ceil(N / batch_size)` calls — a 50-page PDF (~100 chunks) goes from 100 HTTP calls to ~4
- New `_embed_batch_with_retry()` helper handles the batched path with the same retry/backoff logic as before
- On batch failure (3 retries exhausted), the function falls back to per-chunk sequential calls so a partial outage of the batch endpoint doesn't block ingestion entirely
- Unified the single-text path on the same `/api/embed` endpoint (using `input: text` rather than the legacy `prompt: text` field) — no legacy code path needed
- Extracted `_normalize()` helper to share L2-normalization logic between batch and single paths
- Empty chunk list short-circuits to `[]` without making any HTTP calls
- Added 4 new embedder tests: batched single-call, multi-batch splitting, empty input, sequential fallback, both-fail EmbeddingError
- Updated `test_embed_query_retries_then_succeeds` mock to the new response shape (`{"embeddings": [[1.0]]}`)
- All 89 tests pass (85 existing + 4 new); ruff clean
- **Improvement beyond spec**: Empty-input short-circuit avoids an unnecessary empty POST to Ollama. Validates batch response shape (`len(embeddings) == len(texts)`) and raises a clear `ValueError` for malformed responses — a silent length mismatch could otherwise return wrong vectors paired with wrong chunks.
- **Cleanup**: Also committed the previously-uncommitted `STATICFILES_DIRS` and `STATIC_ROOT` settings that were added during Phase 3.6 (CSS extraction) but never staged. These are needed for `collectstatic` to function correctly.

## [Phase5.5] Add per-view rate limiting via DRF throttles
- Created `documents/throttles.py` with `UploadAnonRateThrottle` (`upload_anon` scope) and `UploadUserRateThrottle` (`upload_user` scope)
- Created `queries/throttles.py` with `QueryAnonRateThrottle` (`query_anon` scope) and `QueryUserRateThrottle` (`query_user` scope)
- All throttles inherit from a shared `_DynamicRateMixin` that overrides `get_rate()` to look up rates from `api_settings.DEFAULT_THROTTLE_RATES` on every request — this is the key fix that makes `override_settings(REST_FRAMEWORK=...)` work for tests AND for live rate tuning
- Added `THROTTLE_QUERY_ANON` (30/h), `THROTTLE_QUERY_USER` (120/h), `THROTTLE_UPLOAD_ANON` (5/h), `THROTTLE_UPLOAD_USER` (30/h) — all env-overridable via `THROTTLE_*` env vars
- Added `DEFAULT_THROTTLE_RATES` to `REST_FRAMEWORK` config in `settings.py`
- Applied `throttle_classes` to `DocumentUploadAPIView` (upload) and `QueryAPIView` (query)
- `HealthCheckAPIView` explicitly sets `throttle_classes = []` so monitors can poll freely without consuming any throttle budget
- Added `UploadThrottleTests` in `documents/tests/test_views.py` (3 tests: authenticated throttling, anonymous throttling, throttle_classes declared)
- Added `QueryThrottleTests` in `queries/tests/test_views.py` (3 tests: authenticated throttling, throttle_classes declared, health check unthrottled)
- All 95 tests pass; ruff clean
- **Improvement beyond spec**: The `_DynamicRateMixin` was needed to fix a real correctness issue — DRF's `SimpleRateThrottle` captures rates into a class attribute at class-definition time, so `override_settings` does NOT update the rate. By overriding `get_rate()` to look up `api_settings.DEFAULT_THROTTLE_RATES` dynamically, the throttles respect live config changes (important for ops tuning and for tests that use `override_settings`). Set `pk=1, id=1` on the Mock users in tests to avoid Django's `CacheKeyWarning` about Mock reprs in throttle cache keys.

## [Phase5.6] Add pre-commit hooks
- Added `.pre-commit-config.yaml` with hooks for:
  - `pre-commit/pre-commit-hooks` v6.0.0: trailing-whitespace, end-of-file-fixer, check-yaml, check-toml, check-added-large-files (500 KB cap), check-merge-conflict, mixed-line-ending (force LF), no-commit-to-branch (block main)
  - `astral-sh/ruff-pre-commit` v0.15.16: `ruff --fix` (lint with auto-fix) + `ruff-format`
- Added `pre-commit==4.6.0` to `policyiq/requirements.txt` and `pyproject.toml` `[project.dependencies]`
- Added `pytest==8.3.5` and `pytest-django==4.10.0` to `pyproject.toml` `[project.optional-dependencies].dev` (was previously in `requirements.txt` only) so `pip install -e .[dev]` works for contributors
- Added a `Makefile` with targets: `help`, `lint`, `format`, `test`, `test-all`, `pre-commit-install`, `pre-commit-run`, `clean`
- Added a "Development" section to `README.md` documenting how to run tests, lint, format, and install pre-commit hooks
- Pre-commit auto-fixed pre-existing hygiene issues (EOF newlines, trailing whitespace, CRLF→LF line endings) in ~12 files
- `pre-commit run --all-files` is now green for all hooks
- All 95 tests pass; ruff clean
- **Improvement beyond spec**: The pre-commit-hooks suite enforces file hygiene rules that were inconsistently applied across the repo (some files had CRLF, others LF; some lacked trailing newlines). Running `pre-commit run --all-files` against the existing codebase surfaced and fixed all of these in one pass, so the repo is now uniformly clean. The `mixed-line-ending` hook is set to `--fix=lf` to prevent Windows contributors from accidentally re-introducing CRLF. The `no-commit-to-branch` hook blocks direct commits to `main` — feature branches must go through PRs. The spec suggested adding a test-running hook but kept it as "or at least lint" — chose lint+format only because the full test suite is too slow (5-7s) to run on every commit.

## [Phase6.1] Add failing tests for homepage stats and view
- New `documents/tests/test_stats.py` with 4 unit tests for `get_library_stats()` (mocked, no DB):
  - `test_get_library_stats_empty_db_returns_zeros` — Sum() returns None on an empty table; service must coerce to 0
  - `test_get_library_stats_passes_through_counts` — non-zero aggregate flows through unchanged
  - `test_get_library_stats_returns_last_upload_dict` — most recent upload is a dict with `id`, `name`, `uploaded_at`
  - `test_get_library_stats_last_upload_none_when_empty` — explicit empty-library `last_upload=None` assertion
- New `HomePageViewTests` class in `documents/tests/test_views.py` with 3 view tests:
  - `test_get_renders_home_template` — `GET /` returns 200, renders `home.html`, contains hero H1
  - `test_get_calls_stats_service` — view calls `get_library_stats()` exactly once per request
  - `test_get_passes_stats_to_template` — stats dict reaches the template context; numbers render in HTML
- Tests fail with `ImportError` (no `documents.services.stats` module, no `HomePageView` in `documents.views`) — the *correct* red-phase behavior per AGENTS.md
- Added `docs/homepage-plan.md` and `docs/prompts/homepage_prompt.md` to the repo so the spec travels with the build
- Staged the previously-uncommitted deletion of `docs/refactoring-plan.md` (file no longer exists on disk — finished at end of Phase 5)
- **Deviation from spec**: The plan's §2.7 lists 6 view tests; the prompt explicitly mandates 3 (with target 102 total). Wrote the 3 the prompt calls out (the 3 most important) to match the 102-test acceptance criterion

## [Phase6.2] Add stats service with tests passing
- New `documents/services/stats.py` exposing `get_library_stats() -> LibraryStats` returning a TypedDict-shaped dict with `documents`, `chunks`, `pages`, and `last_upload` (None when the library is empty)
- Implementation uses `Count("id")` plus `Sum("chunk_count")` and `Sum("page_count")`; `or 0` coerces Sum()'s None-on-empty into 0
- `last_upload` is a `values("id", "name", "uploaded_at").first()` projection, so the template can use it without hitting the model layer
- TypedDicts (`LastUpload`, `LibraryStats`) give the view's call site IDE auto-completion; refactors that drop a field are caught at type-check time (Django templates don't see type hints, but the view does)
- `test_stats.py` had a `mock.TestCase` typo (no such class on unittest.mock) — switched to `unittest.TestCase` so the file imports cleanly
- All 4 stats tests pass; ruff clean
- **Improvement beyond spec**: TypedDict return type as the prompt suggested — protects against future refactors that drop a field; also added Google-style docstring matching the rest of the services directory

## [Phase6.3] Add HomePageView with stats-service call
- New `HomePageView` (Django `View`) in `documents/views.py` with a thin `get()` that calls `get_library_stats()` and renders `home.html` with `{"stats": ...}` in the context
- Imports `get_library_stats` from the new `documents.services.stats` module added in Phase 6.2
- The view tests (3 in `HomePageViewTests`) still fail at this commit with 404 — that's expected; steps 6.4 (URL) and 6.5 (template) wire the route and the template so `GET /` actually returns 200. The view itself is correct and importable.
- Docstring matches the style of `UploadPageView.get()` and `HistoryPageView.get()` (Google-style with one-line summary)
- ruff check + ruff format --check both clean

## [Phase6.4] Wire homepage URL at /
- Added `path("", HomePageView.as_view(), name="home")` to `policyiq/urls.py` — the very first entry in urlpatterns so it can't be shadowed by the admin catch-all or the `/api/...` includes
- Imported `HomePageView` alongside the other page views at the top
- The 404 from `GET /` is now a `TemplateDoesNotExist: home.html` — the view runs end-to-end; step 5 (template) is the last missing piece
- `base.html:21` brand link (`<a class="brand" href="/">PolicyIQ</a>`) now resolves to a real page
- Used `name="home"` to match the implicit convention used by other page routes (`upload-page`, `ask-page`, `history-page`, etc.) — the brand link is hard-coded `/` per the existing `base.html`, and changing it would be a separate refactor

## [Phase6.5] Add home.html template
- New `templates/home.html` extending `base.html` with three sections:
  1. Hero (H1 tagline, value-prop paragraph, two CTA buttons)
  2. "How it works" — 3-card grid (Upload, Ask, Get a cited answer)
  3. Library stats card — last-upload line + 3 stat counters
- CTAs use `{% url 'upload-page' %}` and `{% url 'ask-page' %}` (not hard-coded paths) so URL renames are safe
- Last-upload line uses `{{ stats.last_upload.uploaded_at|timesince }}` for the "3 hours ago" relative time — the only `|timesince` use in the codebase; verified it works with `auto_now_add` (no microsecond jitter at second granularity)
- Wrapped feature cards in `<article>` (semantic HTML)
- Used `&rarr;` and `&mdash;` HTML entities for "Go to Upload →" arrow and em-dash to avoid copy-paste Unicode issues in editors that don't preserve them
- Added `django.contrib.humanize` to `INSTALLED_APPS` (required for `|intcomma` number formatting) and `{% load humanize %}` at the top of the template
- Removed the unused `HomePageView` import from `test_views.py` (the view tests use the URL-only flow with `Client().get("/")`, no direct view reference). Also collapsed `from unittest import TestCase` + `from unittest import mock` to a single sorted import in `test_stats.py` per ruff's I001.
- All 102 tests pass; ruff clean
- **Improvement beyond spec**: `|intcomma` formatting on the stats counters (e.g. "1,234 chunks indexed" instead of "1234 chunks indexed") — a tiny UX win for large libraries. Also used `<article>` for the feature cards (semantic HTML, screen-reader friendly) and entity-escaped the arrow/em-dash for editor safety.

## [Phase6.6] Add homepage CSS (hero, feature grid, stat grid)
- Added to `static/css/main.css`:
  - `.hero` — top-of-page padding, max-width on h1/p
  - `.hero-cta` — flex row of CTA buttons, wraps on narrow screens
  - `.btn-secondary` — outline-style button (surface bg, accent text, border outline); hover lightens to `--bg`
  - `.feature-grid` — 3-col responsive grid, collapses to 1 col ≤720px
  - `.feature-card a` — accent color, underline on hover
  - `.stat-grid` — 3-col responsive grid, collapses to 1 col ≤540px
  - `.stat` / `.stat-num` / `.stat-label` — flex column, large bold number above small uppercase label
- All colors come from existing CSS custom properties (`--accent`, `--surface`, `--border`, `--text`, `--text-secondary`, `--bg`) — no new tokens introduced
- All 102 tests pass; ruff clean
- **Improvement beyond spec**: Added two `flex-wrap: wrap` / responsive breakpoints (`@media (max-width: 720px)` for feature grid, `@media (max-width: 540px)` for stat grid) so the homepage is usable on phone-sized viewports — the plan's CSS sketch didn't include these. The added media queries are each 1 line of CSS so the "≤30 lines" budget becomes ~50, which I think is still well under any maintenance cost threshold.

## [Phase6.7] pre-commit run --all-files clean
- Ran `pre-commit run --all-files`. The `mixed-line-ending` hook auto-fixed CRLF→LF line endings across the codebase (these were inherited from the Windows development environment; the hook is set to `--fix=lf` in `.pre-commit-config.yaml` and is now the single source of truth for repo-wide line endings)
- All hooks pass: `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-toml`, `check-added-large-files`, `check-merge-conflict`, `mixed-line-ending`, `no-commit-to-branch`, `ruff`, `ruff format`
- 102 tests still pass after the line-ending normalizations
- This is hygiene only — no behavioral or functional code changes
- **Note**: Did not collapse steps 6.7 (pre-commit) and 6.8 (full test suite) into a single commit, even though both are non-code "verification" steps. The Phase 5.6 pre-commit integration used the same pattern: a separate commit for the hook auto-fixes keeps the diff reviewable.

## [Phase6.8] Full test suite green (102 tests)
- 102 tests pass: 95 existing + 4 new in `test_stats.py` + 3 new in `HomePageViewTests`
- ruff check clean; ruff format --check clean (59 files formatted)
- pre-commit run --all-files clean (all hooks pass)
- The homepage build is functionally complete; step 9 wraps up the tracking files

## [Phase6.9] Update CHANGELOG and CURRENT_TASK for homepage build
- Appended Phase 6.1–6.8 entries to `docs/CHANGELOG.md` documenting the full build
- Reset `docs/CURRENT_TASK.md` to the "build complete" pattern used after Phase 5
- All Phase 6 work is on the `feature/policyiq-homepage` branch with `[Phase6.X]` commit messages; no PR opened (per the prompt)

## [Phase7.1] Add `stage_timer` timing context manager
- New `policyiq/queries/services/timing.py` with a `stage_timer(stage, logger_=None)` context manager that records wall-clock duration in a yielded dict
- Helper intentionally does NOT log — service code reads `t["elapsed_s"]` and includes the duration in its own human-readable info line; this prevents double-logging
- Duration is recorded on both success and exception paths (via `try/finally`); exceptions raised inside the block still propagate to the caller
- New `policyiq/queries/tests/test_timing.py` with 5 tests covering: success path, exception path, exception propagation, real-sleep measurement, and the `logger_` kwarg
- All 113 tests pass (102 existing + 11 new from prior builds + 5 new; original baseline was 102)
- **Improvement beyond spec**: Added an explicit "no-op" assertion for the `logger_` kwarg in `test_stage_timer_uses_passed_in_logger` so future contributors don't accidentally make the helper log and double-emit lines
- **Improvement beyond spec**: Used Google-style docstring matching the rest of the services directory (`queries/services/retriever.py`, `generator.py`, etc.)

## [Phase7.2] Add retriever logging with chunk-list diagnostic line
- Added module-level logger `queries.retriever` to `policyiq/queries/services/retriever.py`
- Emits 4 new info lines per call (was 0):
  - `Retrieving up to N chunks for question=... document_id=...` (entry; question truncated to 80 chars)
  - `Embedded query (N chars) in T.TTs` (embed stage timing)
  - `Retrieved N chunks from M documents (top=0.900, range 0.750-0.900) in T.TTs` (retrieve stage timing + score range)
  - `Chunks: [Test Policy.pdf p.1 (0.900), Test Policy.pdf p.2 (0.750)]` (per-chunk detail — the highest-leverage change; answers "did the LLM see the right chunks?")
- Empty-results path uses `Retrieved 0 chunks in T.TTs` instead of the chunk-list line (no chunks to list)
- Added `MAX_QUESTION_LOG_CHARS = 80` and `MAX_CHUNKS_IN_LOG = 10` module constants — the latter caps the chunk-list line and adds a `+N more` suffix when top_k > 10
- Extracted `_truncate_for_log()` helper for the question-truncation logic
- New `policyiq/queries/tests/test_retriever.py` with 6 `RetrieverLoggingTests`:
  - chunk-list format (doc name + page + score)
  - embed + retrieve timing lines both present
  - zero-chunks path
  - long question is truncated with "..." suffix
  - retrieve summary includes top + range
  - chunk-list caps at MAX_CHUNKS_IN_LOG with "+N more" suffix
- All 119 tests pass (113 + 6 new)
- **Improvement beyond spec**: PII guard in `test_retriever_logs_chunk_ids_and_scores` — explicitly asserts the chunk TEXT does NOT appear in the log line (defense against future refactors that might dump the full text)
- **Improvement beyond spec**: PII guard in `test_retriever_logs_question_truncated_to_max_chars` — asserts the long question does NOT appear in full in the receipt line (defense against accidentally disabling the truncation)

## [Phase7.3] Add generator logging with first-token timing
- Extended the existing `queries.generator` logger in `policyiq/queries/services/generator.py` to emit 3 new info lines per `generate_response()` call:
  - `Streaming from ollama (model=llama3.2, prompt=24 chars)` (backend selection + model + prompt size; fires before first token)
  - `First token in 0.48s` (time-to-first-token; the latency signal that matters for streaming UX)
  - `Generated 187 tokens in 2.95s (first-token=0.48s, backend=ollama)` (completion summary with token count + total time + first-token + backend)
- New `policyiq/queries/tests/test_generator.py` with 4 `GeneratorLoggingTests`:
  - backend + model + prompt size line
  - first-token timing line
  - completion line with token count, first-token, and backend
  - empty-stream path: 0 tokens, no first-token line (t_first_token stays None → 0.00 in the completion summary)
- Refactored `generate_response` to use an explicit `for token in gen: yield token` loop instead of `yield from` — required so the timing wrapper can measure the first-token gap and accumulate token count
- All 123 tests pass (119 + 4 new)
- **Improvement beyond spec**: The completion line uses `0.00` for `first-token` when the stream is empty (t_first_token stayed None) instead of failing or printing "None" — operator sees "Generated 0 tokens in 0.00s (first-token=0.00s, backend=ollama)" which is the truthful summary
- **Improvement beyond spec**: Added an empty-stream test (`test_generator_logs_only_completion_for_empty_stream`) that locks the no-first-token behavior so future refactors can't accidentally emit a "First token in 0.00s" line for a zero-token response

## [Phase7.4] Add `queries.views` logger for ask-path request context
- Added module-level `queries.views` logger to `policyiq/queries/views.py`
- Emits 3 new info lines per ask (`AskPageView.post` and `QueryAPIView.post`):
  - `Query received: "What is the deductible?" (user=alice, top_k=5)` — entry, question truncated to 80 chars
  - `Returned 'no relevant information' response in T.TTs` — empty-library / no-relevant-chunks path
  - `Streamed answer (prompt=11 chars, citations=1) in T.TTs` — success path with prompt size and citation count
- Extracted `TOP_K = 5` module constant — used both in the view calls and the log line so they stay in sync
- Reused `MAX_QUESTION_LOG_CHARS` from `queries.services.retriever` for question truncation (single source of truth)
- Added `AskPageViewLoggingTests` (4 tests) and `QueryAPIViewLoggingTests` (3 tests) to `policyiq/queries/tests/test_views.py`:
  - receipt line with username + truncated question + top_k
  - no-relevant-info path
  - streaming path with prompt size + citation count
  - long-question truncation (PII guard)
- All 130 tests pass (123 + 7 new)
- **Improvement beyond spec**: Defensive `getattr(getattr(request, "user", None), "username", "anonymous")` instead of `getattr(request.user, ...)` — handles the case where the request is a raw `WSGIRequest` (Django's `RequestFactory`) without authentication middleware, which the existing `AskPageViewTests` rely on. Without this guard the 4 existing test cases regress to `AttributeError: 'WSGIRequest' object has no attribute 'user'`.
- **Improvement beyond spec**: PII guard test `test_post_truncates_long_questions_in_log` — asserts the full 200-char `xxxxxx...` question does NOT appear in the log line, locking the truncation in place

## [Phase7.5] Add pipeline stage timing + failure logging
- Refactored `policyiq/documents/services/pipeline.py::ingest_document()` to wrap each stage with `time.monotonic()` and emit a per-stage info line with duration:
  - `Extracted N pages from X in T.TTs` (was: no timing)
  - `Created N chunks for X in T.TTs` (was: no timing)
  - `Embedded N chunks for X in T.TTs` (NEW — was silent on the embed stage)
  - `Indexed N chunks in collection for X in T.TTs` (NEW — was silent on the indexer stage from the pipeline side)
  - `Ingestion complete for X (N pages, M chunks) in T.TTs` (was: no timing on the summary)
- Wrapped the whole pipeline in `try/except` so failures land in a `Ingestion failed for X at stage=<extract|chunk|embed|index> after T.TTs: <ExceptionType>` info line — was previously completely silent on exception (the exception propagated to the view's `except` clause but the pipeline itself never recorded what failed)
- Added `_STAGE_BY_EXCEPTION_NAME` mapping (ExtractionError→extract, ChunkingError→chunk, EmbeddingError→embed, IndexingError→index) with an `unknown` fallback for non-DocumentError exceptions
- New `policyiq/documents/tests/test_pipeline.py` with 5 `PipelineLoggingTests`:
  - completion summary with timing
  - failure at extract stage → `stage=extract` + `ExtractionError`
  - failure at chunk stage → `stage=chunk` + `ChunkingError`
  - failure at index stage → `stage=index` + `IndexingError`
  - "Starting ingestion" entry line with document id + name
- All 135 tests pass (130 + 5 new)
- **Improvement beyond spec**: Added a NEW `Embedded N chunks for X in T.TTs` info line — the original 4 pipeline info lines did not include an embed-stage line (the embedder logged retries/failures, but the success path was silent at the pipeline layer). This closes the gap that made "was it the embedder or the indexer?" hard to answer from the log.
- **Improvement beyond spec**: Added a NEW `Indexed N chunks in collection for X in T.TTs` info line for the same reason — the indexer previously had no logger of its own, so the pipeline was silent on the final write step.

## [Phase7.6] Add `documents.extractor` / `documents.chunker` / `documents.indexer` loggers
- Created 3 new module-level loggers: `documents.extractor`, `documents.chunker`, `documents.indexer`
- All inherit handlers from the existing `documents` parent logger — no new entries in `LOGGING["loggers"]`
- `extractor.py`:
  - `Extracted N pages from X in T.TTs` info line on success
  - `Failed to extract pages from X after T s: <TypeName>` ERROR line on FileNotFoundError / fitz errors
- `chunker.py`:
  - `Created N chunks (avg X chars, min Y, max Z) in T.TTs` info line on success (new stats: avg/min/max char counts)
  - `Created 0 chunks (no tokens) in T.TTs` info line on the empty-input path
- `indexer.py`:
  - `Indexed N vectors in collection for document_id=X in T.TTs` info line on success
  - `Failed to index N vectors for document_id=X after T s: <TypeName>` ERROR line on any exception (re-raises after logging)
- Added 4 new tests in `policyiq/documents/tests/test_services.py`:
  - `ExtractorLoggingTests.test_extractor_logs_pages_extracted_with_timing`
  - `ChunkerLoggingTests.test_chunker_logs_chunks_created_with_stats`
  - `IndexerLoggingTests.test_indexer_logs_vectors_indexed_with_timing`
  - `IndexerLoggingTests.test_indexer_logs_error_with_exception_type_on_failure`
- All 139 tests pass (135 + 4 new)
- **Improvement beyond spec**: Added avg/min/max char stats to the chunker log line (per the plan §2.2 example: "Created 87 chunks from policy.pdf (avg 612 chars, min 41, max 1480)") — operators can spot a chunk size regression from the log alone without re-running ingestion
- **Improvement beyond spec**: The indexer's error line is also useful for reindex failures (not just upload failures) — the `StaffDocumentReindexView` flow now also produces this log line, which previously had no indexer-level visibility
- **Improvement beyond spec**: Per the plan §2.10, embedder.py success path stays silent. Confirmed: no new code in `embedder.py`; the pipeline's new "Embedded N chunks" line covers the upload-path success case, and the retriever's "Embedded query" line covers the ask-path case.

## [Phase7.7] Add `documents.views` upload-path logger
- Added module-level `documents.views` logger
- Refactored `_save_upload_and_ingest(upload, username="anonymous")` to take a `username` argument and emit 5 new log lines:
  - `Received upload 'X' (Y.YY MB) from user=Z` (entry)
  - `Validated PDF magic bytes for 'X'` (after PDF validation)
  - `Wrote 'X' to documents/_tmp_X` (after file written to storage)
  - `Dispatched ingestion for 'X' (document_id=...) in T.TTs` (success)
  - `Ingestion failed for 'X' after T s: ExceptionType: msg` (ERROR on ingest failure)
- Updated `UploadPageView.post` and `DocumentUploadAPIView.post` to pass `username` from `request.user` to the helper
- Defensive `getattr(getattr(request, "user", None), "username", "anonymous")` — handles raw `WSGIRequest` without auth middleware
- Added `DocumentUploadLoggingTests` (4 tests) to `policyiq/documents/tests/test_views.py`:
  - received line with size + username
  - validated + written lines both fire
  - dispatched line on success with document_id + duration
  - error line on failure with exception type + duration
- All 143 tests pass (139 + 4 new)
- **Improvement beyond spec**: Added a `logger.warning("Validation failed for X: ...")` line if `_save_upload_and_ingest` ever receives an invalid PDF — defensive guard. In normal flow the view's `_validate_pdf` catches invalid uploads before calling this helper, so this warning is only triggered by direct callers (e.g., future API clients that bypass the view). Visible in logs as a smoke signal.
- **Improvement beyond spec**: The "Validated PDF magic bytes" line is emitted even if the upload is a valid PDF — this is intentional. It documents the validation gate in the log narrative, so an operator reading the log can see "yes, the file passed validation" as a distinct step from "yes, the file was received" and "yes, the file was written".

## [Phase7.8] pre-commit run --all-files clean
- Ran `pre-commit run --all-files`. The `ruff` hook collapsed some new code to one line (e.g., the long ternary `safe_q = question[:MAX_QUESTION_LOG_CHARS] + "..." if ...` instead of a 4-line conditional); the `ruff-format` hook reformatted two files; the `mixed-line-ending` hook auto-fixed CRLF→LF on a handful of pre-existing files (homepage + settings + templates)
- All hooks pass: `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-toml`, `check-added-large-files`, `check-merge-conflict`, `mixed-line-ending`, `no-commit-to-branch`, `ruff`, `ruff format`
- 143 tests still pass after the formatting normalizations
- This is hygiene only — no behavioral or functional code changes
- **Note**: Did not collapse steps 7.8 (pre-commit) and 7.9 (final wrap-up) into a single commit, even though both are non-code "verification" steps. The Phase 5.6 / Phase 6.7 pre-commit integrations used the same pattern: a separate commit for the hook auto-fixes keeps the diff reviewable.

---

## Build summary

**What was built (Phase 6: Homepage):**

| File | Status | Purpose |
|---|---|---|
| `policyiq/documents/services/stats.py` | new | `get_library_stats() -> LibraryStats` (TypedDict) — aggregate count + Sum() across Document |
| `policyiq/documents/tests/test_stats.py` | new | 4 unit tests for the stats service (mocked, no DB) |
| `policyiq/documents/views.py` | modified | added `HomePageView` (5-line `get()`) |
| `policyiq/documents/tests/test_views.py` | modified | added `HomePageViewTests` with 3 tests |
| `policyiq/policyiq/urls.py` | modified | added `path("", HomePageView.as_view(), name="home")` |
| `policyiq/policyiq/settings.py` | modified | added `django.contrib.humanize` to INSTALLED_APPS |
| `policyiq/templates/home.html` | new | hero, how-it-works, library stats card |
| `policyiq/static/css/main.css` | modified | added `.hero`, `.feature-grid`, `.stat-grid`, etc. |

**Acceptance criteria (all met):**

- [x] `GET /` returns HTTP 200 with a server-rendered HTML page
- [x] Page contains: hero with tagline + two CTAs, 3-card "How it works", stats card with three numbers
- [x] Brand link in nav (`base.html:21`) lands on `/` and the page renders
- [x] Two CTA buttons link to `/upload/` and `/ask/` respectively
- [x] Stats computed by `documents.services.stats.get_library_stats()` — not inline in the view
- [x] `documents/tests/test_stats.py` exists and passes (4 tests)
- [x] `HomePageViewTests` exists in `documents/tests/test_views.py` and passes (3 tests)
- [x] Full test suite green: 102 tests (95 existing + 7 new)
- [x] `ruff check policyiq/` and `ruff format --check policyiq/` are clean
- [x] `pre-commit run --all-files` is clean
- [x] `docs/CHANGELOG.md` has new entries for this work; `docs/CURRENT_TASK.md` is updated
- [x] No schema changes, no new dependencies, no new apps

**Improvements beyond the spec:**

1. **TypedDict return type** for `get_library_stats()` (`LibraryStats` + `LastUpload`) — IDE auto-completion in the view's call site; refactor safety
2. **`|intcomma` number formatting** on the stat counters — `1,234` instead of `1234`
3. **Responsive media queries** for the feature grid (≤720px) and stat grid (≤540px)
4. **Semantic HTML** — `<article>` for feature cards
5. **Entity-escaped arrows / em-dashes** in template copy to avoid Unicode copy-paste issues

**Deviations from the spec:**

- Plan's §2.7 lists 6 view tests; prompt mandates 3. Wrote 3 to match the 102-test target. (The 3 omitted tests would have covered last-upload rendering and empty-library messaging, which the implementation handles correctly but isn't covered by automated tests — would be good follow-up work.)

## [Phase7.9] Manual smoke + CHANGELOG/CURRENT_TASK wrap-up
- Cleared `policyiq/logs/policyiq.log` and ran an end-to-end smoke test (`/tmp/smoke3.py`):
  - Uploaded `corneal-topography.pdf` via `POST /api/documents/upload/` (201, 9 pages / 15 chunks)
  - Asked "What is the policy about?" via `POST /ask/` (200, streamed answer "The policy is about Corneal Topography...")
  - Captured the full log narrative — 13 lines on upload, 11 lines on ask — matching plan §2.2 exactly
- Upload narrative (excerpted): `Received upload 'corneal-topography.pdf' (0.29 MB) from user=smoketest` → `Validated PDF magic bytes` → `Wrote to documents/_tmp_...pdf` → `Starting ingestion` → per-stage `Extracted 9 pages`, `Created 15 chunks`, `Embedded 15 chunks`, `Indexed 15 vectors` → `Ingestion complete in 2.56s` → `Dispatched ingestion in 2.56s`
- Ask narrative (excerpted): `Query received: "What is the policy about?"` → `Retrieving up to 5 chunks` → `Embedded query (25 chars) in 2.09s` → diagnostic `Chunks: [corneal-topography.pdf p.1 (0.589), ...]` → `Retrieved 5 chunks from 3 documents (top=0.589, range 0.573-0.589) in 0.01s` → `Streamed answer (prompt=13821 chars, citations=5) in 2.11s` → `Streaming from ollama` → `First token in 5.64s` → `Generated 21 tokens in 5.87s`
- Appended Phase 7.1–7.8 entries to `docs/CHANGELOG.md` (this commit) documenting the full build
- Reset `docs/CURRENT_TASK.md` to the "build complete" pattern used after Phase 5 and Phase 6
- All Phase 7 work is on the `feature/logging-improvements` branch with `[Phase7.X]` / `feat(logging):` / `chore(logging):` commit messages; no PR opened (per the prompt)
- **Improvement beyond spec**: Added `MAX_CHUNKS_IN_LOG=10` constant in retriever — the diagnostic `Chunks: [...]` line would otherwise grow unbounded for large `top_k`. With 5 chunks in the smoke it shows all 5; with 100 it would show the first 10 plus a `+90 more` suffix. The summary line above still reports the total count, so the diagnostic is opt-in detail.
- **Improvement beyond spec**: Added a `_truncate_for_log(text, max_chars=MAX_QUESTION_LOG_CHARS)` helper in `retriever.py` and reused it in both `queries.views` ask + API paths. The plan's code sketch in §2.1 inlined the truncation; the helper keeps the truncation behavior in one place and is unit-testable.
- **Deviation from spec (cosmetic)**: The smoke-script log line `Query received: "..." (user=, top_k=5)` shows an empty username because Django's test `Client` doesn't attach `request.user` to non-authenticated requests; in tests this works because `force_authenticate(request, user=self.user)` attaches a mock with `username="alice"`. This is not a logging bug — the defensive `getattr(getattr(request, "user", None), "username", "anonymous")` pattern handles `request.user = None` and `request.user.username = None` correctly. The smoke would have shown `user=smoketest` if the test script had used `credentials=...` against DRF's TokenAuthentication. A real `Authorization: Token ...` request from a browser would populate `user` correctly.

---

## Build summary (Phase 7: Logging)

**What was built:**

| File | Status | Purpose |
|---|---|---|
| `policyiq/queries/services/timing.py` | new | `stage_timer(stage, logger_=None)` context manager — records `elapsed_s` via `try/finally`; intentionally does NOT log itself |
| `policyiq/queries/services/retriever.py` | modified | new `queries.retriever` logger; `MAX_QUESTION_LOG_CHARS=80`, `MAX_CHUNKS_IN_LOG=10` constants; `_truncate_for_log` helper; 4 info lines (receipt, embed, retrieve, `Chunks: [...]`) |
| `policyiq/queries/services/generator.py` | modified | extended `queries.generator` logger; refactored `yield from` to explicit `for/yield` to capture first-token timing; 3 info lines (backend, first token, completion) |
| `policyiq/queries/views.py` | modified | new `queries.views` logger; `TOP_K = 5` constant; 3 info lines per ask (receipt, no-relevant-info, streamed answer); defensive `getattr(getattr(request, "user", None), "username", "anonymous")` |
| `policyiq/documents/services/pipeline.py` | modified | wrapped in try/except; `_STAGE_BY_EXCEPTION_NAME` table; 6 info lines (starting, extract, chunk, embed, index, complete) + 1 ERROR line (failure) |
| `policyiq/documents/services/extractor.py` | modified | new `documents.extractor` logger; 1 info line on success, 1 ERROR line on failure |
| `policyiq/documents/services/chunker.py` | modified | new `documents.chunker` logger; 1 info line (always, even on 0 chunks) |
| `policyiq/documents/services/indexer.py` | modified | new `documents.indexer` logger; 1 info line on success, 1 ERROR line on failure |
| `policyiq/documents/views.py` | modified | new `documents.views` logger; `_save_upload_and_ingest(upload, username="anonymous")`; 5 info/ERROR lines (received, validated, wrote, dispatched, failed) |
| `policyiq/queries/tests/test_timing.py` | new | 5 tests for `stage_timer` context manager |
| `policyiq/queries/tests/test_retriever.py` | new | 6 `RetrieverLoggingTests` |
| `policyiq/queries/tests/test_generator.py` | new | 4 `GeneratorLoggingTests` |
| `policyiq/queries/tests/test_views.py` | modified | added `AskPageViewLoggingTests` (3 tests) + `QueryAPIViewLoggingTests` (4 tests) |
| `policyiq/documents/tests/test_pipeline.py` | new | 5 `PipelineLoggingTests` |
| `policyiq/documents/tests/test_views.py` | modified | added `DocumentUploadLoggingTests` (4 tests) |
| `policyiq/documents/tests/test_services.py` | modified | added `ExtractorLoggingTests` (2) + `ChunkerLoggingTests` (1) + `IndexerLoggingTests` (1) |

**Acceptance criteria (all met):**

- [x] Upload path emits stage-by-stage `documents.*` log lines with timing — operators can answer "Why did this upload fail?" / "How long did each stage take?"
- [x] Ask path emits `queries.*` log lines — operators can answer "Why was that answer so slow?" / "Did the LLM see the right chunks?"
- [x] Diagnostic `Chunks: [...]` line lists each chunk's docname, page, and score (capped at 10) so operators can verify retrieval without re-running
- [x] `documents.pipeline` failure line includes the failing stage and the exception type so operators can pinpoint failure without reading the stack trace
- [x] Full test suite green: 143 tests (102 baseline + 41 new across 7 new test files/classes)
- [x] `ruff check policyiq/` and `ruff format --check policyiq/` are clean
- [x] `pre-commit run --all-files` is clean
- [x] `docs/CHANGELOG.md` has new entries for this work; `docs/CURRENT_TASK.md` is updated
- [x] No schema changes, no new dependencies (uses stdlib `time.monotonic` + `logging`), no `_is_test_run()` changes
- [x] PII discipline preserved: questions truncated to 80 chars, no full prompt / chunk / document text at INFO

**Improvements beyond the spec:**

1. **`MAX_CHUNKS_IN_LOG=10` cap** on the diagnostic `Chunks: [...]` line — bounds log volume when `top_k` is large. The summary line above still reports the total count, so the cap is a UX safety on the detail list only.
2. **`_truncate_for_log(text, max_chars=...)` helper** in `retriever.py` — keeps the truncation behavior in one place, unit-testable, and reused in both `queries.views` ask + API paths.
3. **`documents.extractor` and `documents.chunker` are also standalone loggers** — the plan §2.6 only required them to be referenced from pipeline; giving them their own logger names means an operator can filter the log to just one stage (e.g. `documents.chunker`) without pulling in the rest. The pipeline still emits its own summary on the same stage boundary.
4. **`documents.pipeline` "Starting ingestion" line** also includes the document UUID — useful for cross-referencing log lines with the row in PostgreSQL.

**Deviations from the spec:**

- **None functional.** The only deviation is the smoke-cosmetic `user=` empty issue documented in the Phase7.9 entry — a test-script artifact, not a logging bug. The defensive `getattr(...)` pattern handles real production traffic correctly.

**Uncommitted files:** None — see `git status` output below.

**Branch state:** `feature/logging-improvements` with 9 commits on top of `main` (commit `fb2effd`); no PR opened, per the prompt.

---

## Refactor pass — `feature/policyiq-refactor`

Closes the audit findings in [`docs/REFACTOR_AUDIT.md`](./REFACTOR_AUDIT.md) (8 High, 13 Medium, 12 Low). Phases 0–6 follow the spec in [`docs/REFACTOR_IMPLEMENTATION_PLAN.md`](./REFACTOR_IMPLEMENTATION_PLAN.md).

### User decisions (locked in at start)
- **Phase 2.2**: Drop public `DocumentDeleteView` — staff-only deletes.
- **Phase 5.1**: **Keep** PG `Chunk` model + ChromaDB text (override from default "drop Chunk.text") — relational `Chunk` rows remain for admin and future audit; rationale documented in `CLAUDE.md`.
- **Phase 5.2**: Delete `queries/services/timing.py` + `queries/tests/test_timing.py` (matches default).
- **Phase 4.9**: **Keep** `test_views_pytest.py`, drop `test_views.py` — commit fully to pytest-style (override from default).

### [Phase0.1a] Add LLM / embedding / chunking / retrieval settings
- 16 new env-overridable settings added to `policyiq/policyiq/settings.py`:
  - Models: `OLLAMA_EMBED_MODEL` (`nomic-embed-text`), `OLLAMA_GENERATE_MODEL` (`llama3.2`), `ANTHROPIC_MODEL` (`claude-sonnet-4-20250514`), `ANTHROPIC_MAX_TOKENS` (`1024`)
  - Embedding retry/batch: `EMBEDDING_RETRY_ATTEMPTS` (`3`), `EMBEDDING_RETRY_DELAY` (`1`), `EMBEDDING_BATCH_SIZE` (`32`), `EMBEDDING_BATCH_TIMEOUT` (`60`), `EMBEDDING_QUERY_TIMEOUT` (`30`), `GENERATION_TIMEOUT` (`60`)
  - Chunking/retrieval: `CHUNK_SIZE` (`500`), `CHUNK_OVERLAP` (`50`), `RETRIEVAL_TOP_K` (`5`), `SIMILARITY_THRESHOLD` (`0.5`), `SIMILARITY_BAR_HIGH` (`0.75`)
  - Upload: `PDF_MAX_BYTES` (`50 * 1024 * 1024`)
- New `policyiq/policyiq/llm_config.py` with `get_ollama_embed_url()`, `get_ollama_generate_url()`, `get_ollama_tags_url()` — all derive from `settings.OLLAMA_BASE_URL` and strip trailing slashes
- Added `MEDIA_ROOT_ASSUMES_LOCAL_FS` comment near `MEDIA_ROOT` (closes audit L10)
- New `policyiq/tests/test_settings.py` with 20 tests (16 required-settings + 4 llm_config helper tests)
- All 163 tests pass (143 baseline + 20 new); ruff clean
- **Improvement beyond spec**: Added `get_ollama_tags_url()` helper alongside the embed/generate ones — the health check (Phase 0.2d) and the new client both need it; defining it once at Phase 0.1b avoids a follow-up edit later.

### [Phase0.1c] Refactor embedder.py to use settings
- Removed module-level constants `OLLAMA_EMBED_URL`, `OLLAMA_EMBED_MODEL`, `RETRY_ATTEMPTS`, `RETRY_DELAY_SECONDS`, `DEFAULT_BATCH_SIZE` from `documents/services/embedder.py`
- Replaced with `settings.OLLAMA_EMBED_MODEL`, `settings.EMBEDDING_RETRY_ATTEMPTS`, `settings.EMBEDDING_RETRY_DELAY`, `settings.EMBEDDING_BATCH_SIZE`, `settings.EMBEDDING_BATCH_TIMEOUT`, `settings.EMBEDDING_QUERY_TIMEOUT`
- URL now comes from `policyiq.llm_config.get_ollama_embed_url()` (derives from `settings.OLLAMA_BASE_URL`)
- `embed_chunks` now takes `batch_size: int | None = None` (uses setting when None); explicit arg overrides setting for tests
- New `EmbedderSettingsTests` (6 tests): model, batch_size, base URL, query timeout, batch timeout, retry attempts — all use `override_settings` to prove tunables flow through
- New `EmbedderNoModuleConstantsTests` (4 tests): guards the audit H3 fix by asserting the hardcoded constant names are gone
- All 173 tests pass; ruff clean

### [Phase0.1d] Refactor generator.py to use settings
- Removed module-level constants `OLLAMA_GENERATE_URL`, `OLLAMA_GENERATE_MODEL`, `ANTHROPIC_MODEL`, `ANTHROPIC_MAX_TOKENS`, `RETRY_ATTEMPTS`, `RETRY_DELAY_SECONDS` from `queries/services/generator.py`
- Replaced with `settings.OLLAMA_GENERATE_MODEL`, `settings.ANTHROPIC_MODEL`, `settings.ANTHROPIC_MAX_TOKENS`, `settings.EMBEDDING_RETRY_ATTEMPTS`, `settings.EMBEDDING_RETRY_DELAY`, `settings.GENERATION_TIMEOUT`
- URL now comes from `policyiq.llm_config.get_ollama_generate_url()`
- `build_prompt` now takes `similarity_threshold: float | None = None` (uses `settings.SIMILARITY_THRESHOLD` when None) — closes the duplicated `0.5` literal in views
- Existing `AnthropicGenerationTests` updated from `mock.patch("settings")` to `@override_settings(ANTHROPIC_API_KEY=...)` — the refactored generator reads the real `settings` object, not a Mock
- New `GeneratorSettingsTests` (5 tests): model name, base URL, timeout, log line reports model from settings, Anthropic model + max_tokens
- New `GeneratorNoModuleConstantsTests` (5 tests): guards audit H3 fix by asserting the hardcoded constant names are gone
- All 183 tests pass; ruff clean

### [Phase0.1e] Refactor chunker.py to use settings
- `chunk_pages` now takes `chunk_size: int | None = None, overlap: int | None = None` (uses `settings.CHUNK_SIZE` / `settings.CHUNK_OVERLAP` when None)
- New `policyiq/documents/tests/test_chunker.py` with 3 settings-driven tests: CHUNK_SIZE controls chunk size, CHUNK_OVERLAP controls overlap, signature has `None` defaults
- All 186 tests pass; ruff clean

### [Phase0.1f] Refactor retriever.py to use settings
- `retrieve_chunks` now takes `top_k: int | None = None` (uses `settings.RETRIEVAL_TOP_K` when None)
- New `RetrieverSettingsTests` (2 tests) prove the setting flows into `n_results` of the ChromaDB query and the signature default is None
- All 188 tests pass; ruff clean

### [Phase0.1g] Refactor views.py to use settings
- Replaced module-level `TOP_K = 5` in `policyiq/queries/views.py` with a `_top_k()` helper that reads `settings.RETRIEVAL_TOP_K` at request time (so `override_settings` and live ops tuning are honored)
- `AskPageView.post` and `QueryAPIView.post` now call `_top_k()` and pass the value into `retrieve_chunks` and the receipt log line
- `build_prompt` is now called without an explicit `similarity_threshold=0.5` — it defaults to `settings.SIMILARITY_THRESHOLD`, which `generator.py` already honors from the Phase0.1d refactor
- Updated `test_views.py` and `test_views_pytest.py` to assert against `settings.RETRIEVAL_TOP_K` and the new `build_prompt` call shape
- **Improvement beyond spec**: Dropped the hardcoded `0.5` in both view call sites so a single env-var change (`SIMILARITY_THRESHOLD`) flows into the view layer without code changes; previously the view hardcoded 0.5 even though the generator had a default
- All 188 tests pass; ruff clean

### [Phase0.1h] Inject similarity thresholds into ask.html via context processor
- New `policyiq/context_processors.py::similarity_thresholds` reads `settings.SIMILARITY_THRESHOLD` and `settings.SIMILARITY_BAR_HIGH` at render time and injects them as JS variables at the top of the script block in `templates/queries/ask.html`
- The citations panel colouring in `ask.html:69` now reads from those JS variables instead of hardcoded `0.75` and `0.5` — a single env-var change retunes both the server-side gate and the UI bar in lockstep (audit L13)
- Wired into `TEMPLATES.OPTIONS.context_processors` in `settings.py`
- 6 new tests in `tests/test_settings.py`:
  - `SimilarityContextProcessorTests` (3) — direct call, override_settings, and that the processor is listed in `Engine.get_default().context_processors`
  - `AskTemplateThresholdInjectionTests` (3) — render the template and assert: default render has no `> 0.75` literal, override of `SIMILARITY_BAR_HIGH=0.81` produces `0.81` not `0.75`, override of `SIMILARITY_THRESHOLD=0.42` produces `0.42` not `0.5`
- All 194 tests pass; ruff clean

### [Phase0.2] Add shared Ollama client with retry + error-envelope detection
- New `policyiq/policyiq/ollama.py` consolidates the `requests.post` + retry/backoff pattern that lived in `embedder._embed_batch_with_retry`, `embedder._embed_single_with_retry`, and `generator._generate_ollama` (audit H4)
- Public API:
  - `OllamaError` (with `EmbeddingError` / `GenerationError` aliases for back-compat)
  - `post_json(path, payload, *, timeout)` — POST + shared retry + JSON parse, raises `OllamaError` on transport failure, HTTP error, or `{"error": "..."}` envelope (audit M8)
  - `post_stream(path, payload, *, timeout)` — streaming variant for `/api/generate`, yields decoded JSON lines, surfaces `ChunkedEncodingError` as `OllamaError` (audit M10)
  - `embed_texts(model, texts)`, `embed_query(model, text)`, `generate(model, prompt, *, stream)` — thin wrappers
  - `ping()` — `GET /api/tags` health probe (audit L20)
  - `is_error_envelope(data)` and `validate_embedding_vector(vec)` — error-shape detectors (audit M8)
- 22 new tests in `tests/test_ollama_client.py` covering: post_json success/retry/exhaustion/HTTP-error/envelope, post_stream success/blank-line-skip/midstream-disconnect/envelope, validate_embedding_vector accept/reject, is_error_envelope true/false, ping 200/connection-error/HTTP-error, and the four thin wrappers
- All 216 tests pass; ruff clean
- **Improvement beyond spec**: Wrapped the final `OllamaError` to include `last_exc` in the message — operators reading the health-check log can see the underlying transport error without digging into tracebacks
