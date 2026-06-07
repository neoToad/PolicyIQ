# Refactor Build Prompt

You are refactoring PolicyIQ to close every finding in `docs/REFACTOR_AUDIT.md`. The implementation spec is split into seven per-phase files under `docs/prompts/refactor/`. **Read them one at a time, in order, and execute each phase fully before moving to the next.**

You are already on branch `feature/policyiq-refactor`. The first three commits (Phase 0.0, 0.1 settings, 0.1c–0.1f settings refactors) have already landed. Use `docs/CURRENT_TASK.md` to determine which phase is next — if it says "Phase 1 in progress", open `refactor/phase1.md` next.

---

## Git Setup (do this first)

1. If a branch named `feature/policyiq-refactor` does not exist, create it from `main` and check it out.
2. After completing each numbered phase (Phase 0, Phase 1, …, Phase 6), stage all new and modified files, commit, and push.
3. Use this commit message format from `AGENTS.md`:
   ```
   <type>(<scope>): <summary>
   - <what changed>
   ```
   Use `[PhaseN]` as a prefix on the summary line for traceability, e.g. `refactor(pipeline): atomic write order — [Phase1]`.

---

## Phase Execution Order

Read these files in this order. Each file is self-contained: it carries its own TDD steps, commit cadence, and verify checklist. Do not load them all upfront — open one, execute it, commit, push, then open the next.

| # | File | What it does |
|---|---|---|
| 0 | [`refactor/phase0.md`](refactor/phase0.md) | Foundation: shared settings + shared Ollama client. Unblocks every later phase. |
| 1 | [`refactor/phase1.md`](refactor/phase1.md) | Pipeline rollback safety (audit H1). Highest-stakes correctness fix. |
| 2 | [`refactor/phase2.md`](refactor/phase2.md) | Delete-path safety (audit H2). Applies the atomicity pattern from Phase 1. |
| 3 | [`refactor/phase3.md`](refactor/phase3.md) | View → service consolidation: `run_query`, `safe_stream`, `ingest_uploaded_pdf`, `_process_uploads`. |
| 4 | [`refactor/phase4.md`](refactor/phase4.md) | Test coverage batch (audit H7, H8, M7, M9, M10, M11, M12, M14, L1, L8, L11, L13). |
| 5 | [`refactor/phase5.md`](refactor/phase5.md) | Cleanup, dead code, dedup, doc fixes. |
| 6 | [`refactor/phase6.md`](refactor/phase6.md) | Final pass: full test suite, manual smoke, CHANGELOG, CLAUDE.md update, tag. |

For each phase, the file's own "Commit cadence" / "Commit" line tells you the commit messages to use; the `[PhaseN.X]` tag is mandatory on every commit summary line for traceability.

---

## TDD Rules (from AGENTS.md — non-negotiable)

For every change that adds behavior, follow the cycle exactly:
1. Write failing tests first
2. Confirm they fail for the right reasons (e.g., `ImportError` for missing function, `AssertionError` for wrong value)
3. Write minimum code to make them pass
4. Refactor if needed, keeping tests green

Split Django tests by file: view tests → `test_views.py` (or `test_views_pytest.py` per Locked Decision #4), model tests → `test_models.py`, serializer tests → `test_serializers.py`, service-layer tests → `test_<service>.py` (e.g., `test_ollama_client.py`, `test_query_pipeline.py`).

No commit message if tests are failing. Never commit secrets, keys, or credentials.

---

## Locked Decisions

The following four decisions have already been made by the user (see `docs/CURRENT_TASK.md`). **Do NOT call `AskUserQuestion` for these.** Apply them as written:

1. **Phase 2.2 — `DocumentDeleteView` consolidation:** Drop `DocumentDeleteView`. All deletes go through the staff-only path. Update `urls.py:27` and `templates/documents/history.html:31` accordingly.
2. **Phase 5.1 — `Chunk` storage duplication:** **Keep both** — the PG `Chunk` model and the ChromaDB text payloads. This is a user override of the default. Document the rationale in `CLAUDE.md` during Phase 5.1.
3. **Phase 5.2 — `StageTimer` / `timing.py`:** **Delete** `queries/services/timing.py` and `queries/tests/test_timing.py`. Add a `# TODO: shared stage timer` comment at each inline `t0 = time.monotonic()` block in the five services that have them.
4. **Phase 4.9 — `test_views_pytest.py` consolidation:** **Keep `test_views_pytest.py`, drop `test_views.py`.** This is a user override of the default — the project is fully committing to pytest-style for view tests. The `conftest.py` fixtures stay.

---

## Environment Assumptions

- Python 3.11+
- Repo root is the working directory; the Django project root is `policyiq/`
- A virtualenv is active and `pip install -r policyiq/requirements.txt` has been run
- Ollama running at `http://localhost:11434` with `nomic-embed-text` and `llama3.2` already pulled is **not** required — every new test mocks the LLM/embedding boundary
- PostgreSQL is not required for these changes — all tests use the in-memory SQLite test DB

---

## Tracking Files

Maintain two markdown files throughout the entire build. Update them continuously — not just at the end.

### docs/CURRENT_TASK.md
Always reflect exactly what is happening right now, updated before each phase:
- The current phase number and name
- What you are actively working on
- Any blockers or open decisions being made
- What the next phase will be

Overwrite it completely each time you move to a new phase. It should never describe a completed phase — only the live current state.

### docs/CHANGELOG.md
Append an entry after every commit:
- The phase number and commit message
- A plain-English summary of what was built
- Any improvements made beyond the spec (see below)
- Any deviations from the spec and why

---

## Refactoring and Improvements

As you build, use your judgment to add sensible improvements beyond what the spec explicitly describes. Good candidates: better error messages, type hints, docstrings, input validation, DRY service abstractions, defensive handling of edge cases, small UX improvements. Note them in `docs/CHANGELOG.md` under the relevant entry.

If you spot an unrelated bug or dead code while reading a file, **leave it alone** unless it blocks the phase. This build is scoped to closing the audit findings.

---

## Rules

- Complete, commit, and push to remote each phase before starting the next.
- If a phase produces errors, fix them before moving on. Do not proceed on broken code.
- Do not batch multiple phases into one commit.
- Always commit `docs/CURRENT_TASK.md` and `docs/CHANGELOG.md` alongside the phase's code files.
- All `.md` files in this prompt are located in the `docs/` folder.
- New settings live in `policyiq/policyiq/settings.py`. New shared modules live in `policyiq/` (project root) when consumed by multiple apps, and in `policyiq/<app>/services/` when owned by a single app. Each phase ends with a `chore(refactor):` or `docs:` commit if behavior changed.
- `python manage.py test` from inside `policyiq/` (or `pytest` if the project has switched per Locked Decision #4) must be green at the end of each phase.
- `ruff check policyiq/` and `ruff format --check policyiq/` must be clean before the Phase 6 commit.
- `pre-commit run --all-files` must be clean before the Phase 6 commit.
- Do not add new dependencies. `requests` and `functools` are already in use; no need for `httpx` or similar.
- Do not log full prompt text, full question text beyond 80 chars, full chunk text, or full document text at INFO or DEBUG. PII discipline is a hard constraint.

---

## Phase Boundaries

Each phase in the plan is independently mergeable. The dependency chain is:

```
Phase 0 (settings + ollama_client)
   ↓
Phase 1 (pipeline atomicity)
   ↓
Phase 2 (delete atomicity + DocumentDeleteView consolidation)
   ↓
Phase 3 (view → service: run_query, ingest_uploaded_pdf, _process_uploads, safe_stream)
   ↓
Phase 4 (test coverage batch)
   ↓
Phase 5 (cleanup, dead code, dedup, doc fixes)
   ↓
Phase 6 (verify, log, tag)
```

The **minimum viable slice** that closes the **High** findings (H1–H8) is **Phases 0 + 1 + 2 + 3.1 + 3.2**. If you want to ship the high-stakes fixes first, stop after Phase 3.2 and tag a release, then continue with Phases 4–5 in follow-up PRs.

Do not skip ahead. Phase 0 unblocks Phases 1–5; Phase 1 unblocks Phase 2; Phase 3 unblocks Phase 4's view-layer tests.

---

## Verification Checklist Before the Final Commit (Phase 6)

Before writing the Phase 6 commit, confirm:
- [ ] All phases (0–5) are complete and on the `feature/policyiq-refactor` branch.
- [ ] The full test suite is green: `python manage.py test` from inside `policyiq/` (or `pytest` if the project has switched per Locked Decision #4).
- [ ] `ruff check policyiq/` and `ruff format --check policyiq/` are clean.
- [ ] `pre-commit run --all-files` is clean.
- [ ] `docs/CHANGELOG.md` has a new entry summarizing the refactor pass; `docs/CURRENT_TASK.md` is updated to "Build finished" with a brief summary.
- [ ] The `Chunk` storage decision (Locked Decision #2 — keep both) is documented in `CLAUDE.md` with rationale.
- [ ] No schema changes beyond the Phase 5.1 migration (note: per Locked Decision #2 there is no Phase 5.1 migration); no new dependencies; no new apps.

---

## When All Phases Are Complete

- Update `docs/CURRENT_TASK.md` to a brief build-complete summary.
- Confirm all commits are on the `feature/policyiq-refactor` branch with correct `[PhaseN]` prefixes.
- List any files not committed.
- Print a summary of what was built, all improvements made beyond the spec, and any deviations.
- Push the branch to remote.
- Do not open a pull request.
