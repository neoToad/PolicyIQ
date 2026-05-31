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
