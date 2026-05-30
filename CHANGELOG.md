# Changelog

## [Phase1.1] Remove committed `.env` from git history
- Verified `policyiq/.env` is NOT tracked in git (already properly ignored by `.gitignore`)
- Verified no `.env` content exists in git history (never committed)
- Added `!.env.example` negation rule to `.gitignore` so template file isn't ignored
- Created `policyiq/.env.example` as a safe template for new developers (no real secrets)
- Fixed `.gitignore` — removed overly broad `documents/` pattern that would ignore the Django app
- Added `/documents/` (root-anchored) to ignore repo-root sample PDFs without ignoring `policyiq/documents/`
- **Deviation from spec**: `git filter-repo` not needed since `.env` was never committed; password rotation is a manual step for the user to perform
