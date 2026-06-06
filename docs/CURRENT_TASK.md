# Current Task

**Build status: IN PROGRESS — Phase 7 (Logging improvements), Step 7.5**

## Active step
**Step 7.5 — Add stage timing + failure logging to `documents.pipeline`**

## What is happening now
- TDD red phase: creating new `policyiq/documents/tests/test_pipeline.py`
  with `PipelineLoggingTests`. Tests per the plan §2.8:
  1. `test_pipeline_logs_stage_lines_with_timing` — each stage's
     logger emits its info line with a duration field
  2. `test_pipeline_logs_failure_at_correct_stage` — chunker raises
     `ChunkingError`; assert the error line identifies the stage + type
  3. `test_pipeline_logs_completion_summary` — final "Ingestion
     complete" line on success includes the duration
- The existing `ingest_document` has 4 info lines; we need to add
  `in T.TTs` suffixes (matching the pattern from other steps) and
  wrap the whole thing in a try/except for failure logging
- The pipeline's existing 4 logger.info lines already log; need to
  augment with stage-level timing

## TDD rules in effect
- Red → confirm red → green → refactor → commit
- New test file is `test_pipeline.py` (per plan §2.3) — separate from
  `test_services.py` to follow the `test_<service>.py` convention

## Blockers / decisions
- Decision: Use the existing `documents.pipeline` logger (no new module
  logger) and add timing info to the existing 4 info lines
- Need `ChunkingError` exception class — verify it exists in
  `documents/exceptions.py` (was added in Phase 5.2 per CHANGELOG)

## Next step
**Step 7.6 — extractor/chunker/indexer logger creation + lines + tests**
(one file at a time, per the plan)
