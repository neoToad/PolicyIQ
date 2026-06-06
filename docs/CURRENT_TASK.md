# Current Task

**Build status: IN PROGRESS — Phase 7 (Logging improvements), Step 7.7**

## Active step
**Step 7.7 — Add `documents.views` logger for upload-path request context**

## What is happening now
- TDD red phase: writing `DocumentUploadLoggingTests` in
  `policyiq/documents/tests/test_views.py` (extending the existing file —
  view tests belong there per AGENTS.md)
- Tests per the plan §2.8:
  1. `test_upload_logs_received_line` — "Received upload 'X' (Y MB) from user=Z"
  2. `test_upload_logs_validated_and_written_lines` — both intermediate lines
  3. `test_upload_logs_dispatched_line_on_success` — "Dispatched ingestion
     for X (document_id=Y) in T s"
  4. `test_upload_logs_error_with_exception_type_on_failure` — "Ingestion
     failed for X after T s: ExceptionType: msg" ERROR line
- The view layer is the only place that knows the request context
  (user, file size, content-type, status)

## TDD rules in effect
- Red → confirm red → green → refactor → commit
- All log lines go through `assertLogs("documents.views", level="INFO")`
  or `assertLogs("documents.views", level="ERROR")` for the failure case
- The 4 existing `DocumentUploadAPITests` cases use mocked `ingest_document`
  and need to be verified to still pass

## Blockers / decisions
- None yet. The view-layer logging wraps the existing `_save_upload_and_ingest`
  helper, not the view methods directly — keeps the logging close to the
  actual ingestion orchestration

## Next step
**Step 7.8 — pre-commit + full test run** (final verification gate)
