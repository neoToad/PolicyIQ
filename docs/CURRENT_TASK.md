# Current Task

**Build status: COMPLETE — All 9 steps of Phase 7 (Logging improvements) done.**

## What was finished
- `feature/logging-improvements` branch created from `main`; 9 commits pushed (`[Phase7.1]` through `[Phase7.9]`)
- New `queries/services/timing.py` with `stage_timer` context manager
- New `queries/tests/test_timing.py` (5 tests)
- New logger: `queries.retriever` — 4 info lines including the diagnostic `Chunks: [...]` line (6 tests)
- Extended logger: `queries.generator` — backend + first-token + completion lines (4 tests)
- New logger: `queries.views` — receipt, no-relevant-info, streamed-answer lines (7 tests)
- New logger: `documents.pipeline` — stage timing on all 5 stages + failure line (5 tests)
- New loggers: `documents.extractor`, `documents.chunker`, `documents.indexer` (4 tests)
- New logger: `documents.views` — upload-path narrative (4 tests)
- New `documents/tests/test_pipeline.py` (5 tests)
- New `MAX_QUESTION_LOG_CHARS` and `MAX_CHUNKS_IN_LOG` constants in retriever
- Manual smoke verified end-to-end: uploaded a PDF, asked a question, observed the full log narrative (13 lines on upload, 11 lines on ask) in `policyiq/logs/policyiq.log`

## Verification
- **143 tests pass** (102 baseline + 41 new across 7 new test files/classes)
- `ruff check policyiq/` — clean
- `ruff format --check policyiq/` — clean
- `pre-commit run --all-files` — all hooks pass

## Next step
None — the logging build is shipped. Future work (out of scope for this build):
- Per-test logger capture is via `assertLogs` context manager; consider a `caplog` pytest fixture shim for consistency between pytest and Django runner
- The pipeline emits both `documents.pipeline` and per-stage `documents.{extractor,chunker,indexer}` lines for each stage (by design — different audiences). A future cleanup could let one of them go, but per the plan both are intentional.
- The `documents.pipeline` log line shows the full path (e.g. `C:\Users\...\\_tmp_X.pdf`) in the extractor's `Extracted N pages from PATH` line. This is a Windows-specific path leak. Could be replaced with just the basename, but the plan §2.2 sketch shows the full path so we kept it.

