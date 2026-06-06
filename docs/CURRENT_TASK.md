# Current Task

**Build status: IN PROGRESS — Phase 7 (Logging improvements), Step 7.4**

## Active step
**Step 7.4 — Add `queries.views` logger + `QueryLoggingTests`**

## What is happening now
- TDD red phase: writing tests in `policyiq/queries/tests/test_views.py`
  (extending the existing file — view tests belong there per AGENTS.md)
- The `QueryLoggingTests` class will cover:
  1. `test_query_logs_received_line_with_truncated_question` — `Query
     received: "..."` line, 80-char truncation, username included
  2. `test_query_logs_no_relevant_info_path` — `Retrieved 0 chunks`,
     `No relevant information`, view's "Returned ... response" line
  3. `test_query_logs_streaming_response_with_prompt_size` — `Streamed
     answer (prompt=N chars, M citations) in T.TTs` line on success
- The view layer is the only place that has request context (user, etc.)
- Need to be careful: tests use Mock users, so `getattr(user,
  "username", "anonymous")` will return a Mock repr — but the logger
  output goes to cm.output as the formatted string, so the assertion is
  on substring presence

## TDD rules in effect
- Red → confirm red → green → refactor → commit
- All log lines go through `assertLogs("queries.views", level="INFO")`

## Blockers / decisions
- None yet. Both `AskPageView.post` and `QueryAPIView.post` will get
  logging — per the plan, the view layer is the natural place for
  request-context lines

## Next step
**Step 7.5 — pipeline.py stage timing + failure logging** (the existing 4
info lines get `in T.TTs` suffixes + new failure path)
