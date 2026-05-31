# Current Task

**Step**: 2.3 — Extract shared ingestion pipeline
**Status**: Starting
**What I'm doing**: Extracting the duplicated extraction/clean/chunk/embed/index pipeline from `_save_upload_and_ingest()` and `StaffDocumentReindexView` into a shared `documents/services/pipeline.py` service
**Blockers/Decisions**: Need to decide the exact function signature and error handling strategy for the shared `ingest_document()` function
**Next step**: 2.4 — De-duplicate citation construction
