You are implementing the logging improvements for PolicyIQ. Start by reading these documents:
- [logging-plan.md](../logging-plan.md)
- [AGENTS.md](../../AGENTS.md) — at the repo root, contains the TDD rules and commit message format you must follow

The logging plan is your implementation spec — execute every step in §2.9 (Implementation order), in order. Mark the step as completed in the file after it has been completed.

---

## Git Setup (do this first)

1. If a branch named `feature/logging-improvements` does not exist, create it from main and check it out.
2. After completing each numbered step in the prompt plan (7.1, 7.2, 7.3, etc.), stage all new and modified files, commit, and push.
3. Use this commit message format from `AGENTS.md`:
   ```
   <type>(<scope>): <summary>
   - <what changed>
   ```
   Types: `feat` `fix` `test` `refactor` `chore` `docs`. The recommended type for these steps is `feat` (new behavior) or `test` (when only tests are added in the red phase).

---

## TDD Rules (from AGENTS.md — non-negotiable)

For every new feature, follow the cycle exactly:
1. Write failing tests first
2. Confirm they fail for the right reasons (e.g., `ImportError` for missing function, `AssertionError` for missing log line)
3. Write minimum code to make them pass
4. Refactor if needed, keeping tests green

Split Django tests by file:
- View tests → `test_views.py`
- Model tests → `test_models.py`
- Serializer tests → `test_serializers.py`
- Service-layer tests → `test_<service>.py` (e.g., `test_retriever.py`, `test_generator.py`)

No commit message if tests are failing. Never commit secrets, keys, or credentials.

---

## Environment Assumptions

- Python 3.11+
- PostgreSQL running locally, database `policyiq`, user `policyiq_user` (not required for these steps — all new tests use in-memory SQLite via the existing `_is_test_run()` override)
- Ollama running at http://localhost:11434 with `nomic-embed-text` and `llama3.2` already pulled (not required — the new tests mock all LLM/embedding calls)
- Repo root is the working directory

---

## Test Override Notes (read carefully)

The existing `_is_test_run()` shim in `policyiq/policyiq/settings.py:195-197` forces the `documents` and `queries` loggers to `ERROR` during test runs. Django's `assertLogs` context manager overrides the logger level for the duration of the `with` block, so new logging tests that need to see `INFO` lines should use the pattern:

```python
with self.assertLogs("queries.retriever", level="INFO") as cm:
    retrieve_chunks(...)
self.assertIn("Retrieved 5 chunks", cm.output[0])
```

Do not change the `_is_test_run()` mechanism. Do not add new entries to `LOGGING["loggers"]`. The new module-level loggers (`documents.views`, `documents.extractor`, `documents.chunker`, `documents.indexer`, `queries.views`, `queries.retriever`) inherit handlers from the existing `documents` / `queries` parent loggers — that is enough.

---

## Tracking Files

Maintain two markdown files throughout the entire build. Update them continuously — not just at the end.

### docs/CURRENT_TASK.md
Keep this file up to date at all times. It should always reflect exactly what is happening right now and should be updated
before working on the step:
- The current step number and name
- What you are actively working on
- Any blockers or decisions being made
- What the next step will be

Overwrite it completely each time you move to a new step. It should never describe a completed step — only the live current state.

### docs/CHANGELOG.md
Append an entry after every commit. Each entry should include:
- The step number and commit message
- A plain-English summary of what was built
- Any refactors or improvements made beyond the spec (see below)
- Any deviations from the spec and why


---

## Refactoring and Improvements

As you build, use your judgment to refactor and add sensible improvements beyond what the spec explicitly describes. Good candidates include: better error messages, type hints, docstrings, input validation, DRY service abstractions, defensive handling of edge cases, or small UX improvements in templates. You do not need to ask permission for these — just do them and note them in CHANGELOG.md under the relevant entry.

Examples of acceptable in-scope improvements for this build:
- If `pipeline.py`'s four existing `logger.info` lines need to be re-shaped to include durations consistently with the new helper, do it — but log the change in CHANGELOG.md.
- If a test for `assertLogs` would be cleaner with a small helper (e.g., `assert_log_contains(caplog, "needle")`), extract it. Note it.
- If you spot an unrelated bug or dead code while reading a file, **leave it alone** unless it blocks the step. This build is logging-only.

---

## Rules

- Complete, commit, and push to remote each step before starting the next.
- If a step produces errors, fix them before moving on. Do not proceed on broken code.
- Do not batch multiple steps into one commit.
- Always commit CURRENT_TASK.md and CHANGELOG.md alongside the step's code files.
- All md files are located in the docs folder.
- Keep the test-run logger override (`_is_test_run()`) untouched.
- Do not add new dependencies. `time.monotonic` is in stdlib; `logging` is already configured.
- Do not add a `QueryLog` model, do not add a migration, do not touch `models.py`.
- Do not log full prompt text, full question text beyond 80 chars, full chunk text, or full document text at INFO or DEBUG. PII discipline is a hard constraint.

---

## When All Steps Are Complete

- Update CURRENT_TASK.md to reflect that the build is finished.
- Confirm all commits are on the branch with correct messages.
- List any files not committed.
- Print a summary of what was built, all improvements made beyond the spec, and any deviations.
- Push the branch to remote.
- Do not open a pull request.
