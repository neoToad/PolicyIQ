# Current Task

**Build status: IN PROGRESS — Phase 7 (Logging improvements), Step 7.6**

## Active step
**Step 7.6 — Add `documents.extractor` / `documents.chunker` / `documents.indexer` loggers + info/error lines**

## What is happening now
- TDD red phase: writing 3 new tests in
  `policyiq/documents/tests/test_services.py` (extending the existing
  service-test file — one test per service, plus an error test for the
  indexer):
  1. `test_extractor_logs_pages_extracted_with_timing` — info line on success
  2. `test_chunker_logs_chunks_created_with_stats` — info line on success
  3. `test_indexer_logs_vectors_indexed_with_timing` — info line on success
  4. `test_indexer_logs_error_with_exception_type_on_failure` — error line
- Per the plan §2.10, embedder.py success path stays silent (the pipeline
  already logs at the embed stage). Only the 3 above modules need new
  module-level loggers.

## TDD rules in effect
- Red → confirm red → green → refactor → commit
- All log lines go through `assertLogs("documents.{extractor,chunker,indexer}", level="INFO")`

## Blockers / decisions
- Decision: Add a single `ChunkingError`-style error path test for the
  indexer (the plan mentions both success and error lines for indexer).
  The extractor's existing code re-raises built-in exceptions
  (FileNotFoundError, ValueError) and doesn't have a custom
  ExtractionError path — so we don't need a new "extractor error" test
  beyond what the pipeline failure test already covers.

## Next step
**Step 7.7 — documents.views upload logging + tests** (the view-layer
narrative: received → validated → wrote → dispatched → failure)
