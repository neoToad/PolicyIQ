You are refactoring PolicyIQ to close the findings in `docs/REFACTOR_AUDIT.md`. Start by reading:
- [REFACTOR_IMPLEMENTATION_PLAN.md](../REFACTOR_IMPLEMENTATION_PLAN.md) — your implementation spec
- [REFACTOR_AUDIT.md](../REFACTOR_AUDIT.md) — the findings each phase closes
- [AGENTS.md](../../AGENTS.md) — TDD rules and commit format

Execute every phase in the plan (Phase 0 through Phase 6), in order. Mark the current phase in `docs/CURRENT_TASK.md` as you progress.

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

## TDD Rules (from AGENTS.md — non-negotiable)

For every change that adds behavior, follow the cycle exactly:
1. Write failing tests first
2. Confirm they fail for the right reasons (e.g., `ImportError` for missing function, `AssertionError` for wrong value)
3. Write minimum code to make them pass
4. Refactor if needed, keeping tests green

Split Django tests by file: view tests → `test_views.py`, model tests → `test_models.py`, serializer tests → `test_serializers.py`, service-layer tests → `test_<service>.py` (e.g., `test_ollama_client.py`, `test_query_pipeline.py`).

No commit message if tests are failing. Never commit secrets, keys, or credentials.

---

## Environment Assumptions

- Python 3.11+
- Repo root is the working directory; the Django project root is `policyiq/`
- A virtualenv is active and `pip install -r policyiq/requirements.txt` has been run
- Ollama running at `http://localhost:11434` with `nomic-embed-text` and `llama3.2` already pulled is **not** required — every new test mocks the LLM/embedding boundary
- PostgreSQL is not required for these changes — all tests use the in-memory SQLite test DB

---

## Open Decisions (answer these before starting the matching phase)

The plan flags four decisions that need your call before those phases can start. Defaults are listed; confirm or override:

1. **Phase 5.1 — Chunk storage duplication:** drop `Chunk.text`, drop `Chunk` entirely, or keep both? *Default: drop `Chunk.text` (keeps the relational model, removes the duplication).*
2. **Phase 2.2 — `DocumentDeleteView` consolidation:** drop the public view (staff only) or keep with `LoginRequiredMixin` + owner check? *Default: drop (the public path looks accidental).*
3. **Phase 5.2 — `StageTimer`:** adopt in services or delete `timing.py` + `test_timing.py`? *Default: delete (the inline `t0 = time.monotonic()` blocks are clear enough).*
4. **Phase 4.9 — `test_views_pytest.py`:** keep pytest-style and remove `test_views.py`, or the reverse? *Default: keep `test_views.py` (Django `TestCase` is the project standard per `AGENTS.md`).*

Use `AskUserQuestion` to confirm each before starting the matching phase. Note the answer in `docs/CURRENT_TASK.md`.

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
- Do not add new dependencies. `requests` and `functools` are already in use; no need for `httpx` or similar.
- Do not log full prompt text, full question text beyond 80 chars, full chunk text, or full document text at INFO or DEBUG. PII discipline is a hard constraint.

---

## Phase Boundaries

Each phase in the plan is independently mergeable. The minimum viable slice that closes the **High** findings is **Phases 0 + 1 + 2 + 3.1 + 3.2** — if you want to ship the high-stakes fixes first, stop after Phase 3.2 and tag a release, then continue with Phases 4–5 in follow-up PRs.

Do not skip ahead. Phase 0 unblocks Phases 1–5; Phase 1 unblocks Phase 2; Phase 3 unblocks Phase 4's view-layer tests.

---

## Verification Checklist Before the Final Commit (Phase 6)

Before writing the Phase 6 commit, confirm:
- [ ] All phases (0–5) are complete and on the `feature/policyiq-refactor` branch.
- [ ] The full test suite is green: `python manage.py test` from inside `policyiq/` (or `pytest` if the project has switched).
- [ ] `ruff check policyiq/` and `ruff format --check policyiq/` are clean.
- [ ] `pre-commit run --all-files` is clean.
- [ ] `docs/CHANGELOG.md` has a new entry summarizing the refactor pass; `docs/CURRENT_TASK.md` is updated to "Build finished" with a brief summary.
- [ ] The Chunk storage decision (from Open Decision 1) is documented in `CLAUDE.md`.
- [ ] No schema changes beyond the Phase 5.1 migration; no new dependencies; no new apps.

---

## When All Phases Are Complete

- Update `docs/CURRENT_TASK.md` to a brief build-complete summary.
- Confirm all commits are on the branch with the correct `[PhaseN]` prefixes.
- List any files not committed.
- Print a summary of what was built, all improvements made beyond the spec, and any deviations.
- Push the branch to remote.
- Do not open a pull request.
