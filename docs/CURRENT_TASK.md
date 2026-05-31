# Current Task

**Step**: 2.3 — Extract shared ingestion pipeline
**Status**: In progress (tests fixed, ready to commit)
**What I'm doing**: 
- Extracted duplicated extraction/clean/chunk/embed/index pipeline into `documents/services/pipeline.py` as `ingest_document()`
- Refactored `_save_upload_and_ingest()` and `StaffDocumentReindexView` to use the shared service
- Fixed `StaffDocumentReindexViewTests` to mock `ingest_document` instead of 7 individual services
- Changed `DocumentUploadAPITests` to `TestCase` (Phase 4.2) since `_save_upload_and_ingest` creates real `Document` records
- Added SQLite in-memory test DB override in `settings.py` so `TestCase` tests run without PostgreSQL privileges
- Removed stray PDF artifacts from `policyiq/documents/`

**Blockers/Decisions**: None

**Next step**: Commit Phase 2.3, then move to 2.4 — De-duplicate citation construction
