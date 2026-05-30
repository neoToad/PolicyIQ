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
