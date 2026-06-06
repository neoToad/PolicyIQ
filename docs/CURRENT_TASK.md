# Current Task

**Build status: IN PROGRESS — Phase 7 (Logging improvements), Step 7.3**

## Active step
**Step 7.3 — Add `queries.generator` info lines + `GeneratorLoggingTests`**

## What is happening now
- TDD red phase: writing `policyiq/queries/tests/test_generator.py` with
  `GeneratorLoggingTests`. Tests per the plan §2.8:
  1. `test_generator_logs_backend_and_prompt_size` — the
     "Streaming from ollama (model=llama3.2, prompt=N chars)" line
  2. `test_generator_logs_first_token_timing` — "First token in T.TTs"
  3. `test_generator_logs_completion_with_token_count` — "Generated N tokens in T.TTs"
- The existing `generate_response` function in `queries/services/generator.py`
  already has a `queries.generator` logger; we're extending it
- The existing `test_services.py` has `GenerateResponseTests` —
  the new tests go in a separate `test_generator.py` to follow AGENTS.md
  convention (`test_<service>.py`)

## TDD rules in effect
- Red → confirm red → green → refactor → commit
- All log lines go through `assertLogs("queries.generator", level="INFO")`

## Blockers / decisions
- None yet. Note from the plan §2.11: "First token" timing is measured
  from start of `generate_response()`; if the iterator isn't consumed
  (e.g., test only calls the function but doesn't iterate), the line
  will never fire — the tests must consume the iterator to verify

## Next step
**Step 7.4 — queries.views logging + tests** (request context lives here)
