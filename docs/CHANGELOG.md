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
