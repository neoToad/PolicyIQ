# Current Task

**Build status: IN PROGRESS — Phase 7 (Logging improvements), Step 7.1**

## Active step
**Step 7.1 — Add `policyiq/queries/services/timing.py` with `stage_timer` context manager + failing tests in `test_timing.py`**

## What is happening now
- Branch `feature/logging-improvements` created from `main` (no remote push yet; will push after first commit)
- TDD red phase: writing `policyiq/queries/tests/test_timing.py` with `StageTimerTests` that imports `stage_timer` from `policyiq.queries.services.timing` — expected to fail with `ImportError: cannot import name 'stage_timer'`
- Three tests per the plan §2.8: elapsed_s positive on success, elapsed_s recorded on exception, exception still propagates
- No `queries/tests/test_timing.py` exists yet; safe to add

## TDD rules in effect
- Red → confirm red → green → refactor → commit
- Each step is one commit; current step commit message format: `feat(logging): add stage_timer context manager helper` + matching CHANGELOG entry
- Test files follow AGENTS.md convention: `policyiq/queries/tests/test_timing.py` (service-layer tests)

## Blockers / decisions
- None yet

## Next step
**Step 7.2 — Retriever logging + tests** (highest-leverage; the chunk-listing test locks the diagnostic contract)
