You are building the PolicyIQ homepage. Start by reading documents:
- [homepage-plan.md](../homepage-plan.md)

The homepage plan is your implementation spec — execute every step in §2.8 in order, in TDD red-first style. Mark the plan as completed in CURRENT_TASK.md after the build is done.

---

## Git Setup (do this first)

1. If a branch named `feature/policyiq-homepage` does not exist, create it from `main` and check it out.
2. After completing each numbered step in §2.8 of the plan, stage all new and modified files, commit, and push.
3. Use this commit message format: `[Phase6.X] Short description of what was built` (e.g. `[Phase6.2] Add stats service with tests`).

---

## Environment Assumptions

- Python 3.11+
- PostgreSQL running locally, database `policyiq`, user `policyiq_user`
- Ollama running at http://localhost:11434 with `nomic-embed-text` and `llama3.2` already pulled (the homepage itself does not touch the LLM, but the local stack must be runnable for `make test` / `python manage.py test`)
- Repo root is the working directory
- The `policyiq/` subdirectory is the Django project root; `manage.py` lives there
- A virtualenv is active and `pip install -r policyiq/requirements.txt` has been run

---

## Tracking Files

Maintain two markdown files throughout the entire build. Update them continuously — not just at the end.

### docs/CURRENT_TASK.md
Keep this file up to date at all times. It should always reflect exactly what is happening right now and should be updated before working on the step:
- The current step number (matching §2.8 of the plan) and name
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

## Step Numbering Convention

§2.8 of the plan lists 10 steps as a flat list. Use these commit numbers:

| Plan step | Commit | Message |
|---|---|---|
| §2.8 step 1 (red tests) | `[Phase6.1]` | `Add failing tests for homepage stats and view` |
| §2.8 step 2 (stats service) | `[Phase6.2]` | `Add stats service with tests passing` |
| §2.8 step 3 (HomePageView) | `[Phase6.3]` | `Add HomePageView with tests passing` |
| §2.8 step 4 (URL route) | `[Phase6.4]` | `Wire homepage URL at /` |
| §2.8 step 5 (template) | `[Phase6.5]` | `Add home.html template` |
| §2.8 step 6 (CSS) | `[Phase6.6]` | `Add homepage CSS (hero, feature grid, stat grid)` |
| §2.8 step 7 (pre-commit) | `[Phase6.7]` | `pre-commit run --all-files clean` |
| §2.8 step 8 (full suite) | `[Phase6.8]` | `Full test suite green (102 tests)` |
| §2.8 step 9 (tracking files) | `[Phase6.9]` | `Update CHANGELOG and CURRENT_TASK for homepage build` |

If you collapse any of these (e.g., the URL and template land in the same commit because they trivially go together), renumber sequentially and note the collapse in CHANGELOG.md. Do not skip numbers.

---

## TDD Discipline (per AGENTS.md)

The homepage plan is a *new feature*. AGENTS.md mandates test-first:

1. **Red:** Write the new test cases listed in §2.7 of the plan (4 in `test_stats.py`, 3 in `HomePageViewTests`). Run the suite. Confirm the new tests fail for the *right* reasons (import errors, missing view, template not found, attribute errors on the not-yet-written service) — not for unrelated reasons like a syntax error in your test file.
2. **Green:** Write the minimum code to make the failing tests pass. Do not add behavior beyond what the tests demand.
3. **Refactor:** Only after green. If you spot duplication, unclear naming, or an obvious cleanup, do it now while tests are still passing.
4. **Repeat** for the next layer (service → view → URL → template → CSS).

When in doubt about whether to add a test: add it. The plan's test list is the floor, not the ceiling.

---

## Refactoring and Improvements

As you build, use your judgment to refactor and add sensible improvements beyond what the spec explicitly describes. Good candidates include: better error messages, type hints, docstrings, input validation, DRY service abstractions, defensive handling of edge cases, or small UX improvements in templates. You do not need to ask permission for these — just do them and note them in CHANGELOG.md under the relevant entry.

Specific candidates the homepage build may surface:
- The new `get_library_stats()` service might benefit from a `TypedDict` return type for IDE auto-completion on `stats.last_upload.name` in the template context. (Django templates don't see type hints, but the view's call site will.)
- The `HomePageView.get()` method should have a docstring matching the style of `UploadPageView.get()` and `HistoryPageView.get()`.
- The CSS additions should use existing CSS custom properties (`--accent`, `--surface`, `--border`, etc.) — no new color tokens unless one is genuinely missing.
- The "Last upload: <name>, <time> ago" line is the only place in the codebase that uses the `|timesince` filter — verify it renders correctly with `uploaded_at` set to `auto_now_add` (which has no microsecond jitter issue at second granularity).

---

## Rules

- Complete, commit, and push to remote each step before starting the next.
- If a step produces errors, fix them before moving on. Do not proceed on broken code.
- Do not batch multiple steps into one commit. One logical change per commit.
- Always commit `docs/CURRENT_TASK.md` and `docs/CHANGELOG.md` alongside the step's code files (i.e., they ride with whichever step they were updated in — not bundled into a "tracking" commit at the end).
- All `.md` files in this prompt are located in the `docs/` folder. The implementation steps in the plan may reference `docs/CURRENT_TASK.md` — same path, just the file's location.
- The full test suite must be green before declaring any step done. Per `pyproject.toml` and the test configuration, `python manage.py test` from inside the `policyiq/` directory runs all 95 existing tests in ~0.05s on the in-memory SQLite test DB; the build target after all 7 new tests land is **102 tests passing**.
- `ruff check policyiq/`, `ruff format --check policyiq/`, and `pre-commit run --all-files` must all be clean before the final commit.

---

## Verification Checklist Before the Final Commit

Before writing `[Phase6.9] Update CHANGELOG and CURRENT_TASK for homepage build`, walk through the §4 Acceptance Criteria in the plan and confirm each item is true:

- [ ] `GET /` returns HTTP 200 with a server-rendered HTML page.
- [ ] The page contains: a hero with a tagline and two CTAs, a three-card "How it works" section, and a stats card with three numbers.
- [ ] The brand link in the nav (`base.html:21`) lands on `/` and the page renders.
- [ ] The two CTA buttons link to `/upload/` and `/ask/` respectively.
- [ ] The stats are computed by `documents.services.stats.get_library_stats()` — not inline in the view.
- [ ] `documents/tests/test_stats.py` exists and passes (4 tests).
- [ ] `HomePageViewTests` exists in `documents/tests/test_views.py` and passes (3 tests).
- [ ] The full test suite is green: **102 tests** (95 existing + 7 new).
- [ ] `ruff check policyiq/` and `ruff format --check policyiq/` are clean.
- [ ] `pre-commit run --all-files` is clean.
- [ ] `docs/CHANGELOG.md` has a new entry for this work; `docs/CURRENT_TASK.md` is updated to "Next step: None" once the build is complete.
- [ ] No schema changes, no new dependencies, no new apps.

If any item is unchecked, fix it before the final commit.

---

## When All Steps Are Complete

- Update `docs/CURRENT_TASK.md` to reflect that the build is finished and `docs/CURRENT_TASK.md` should be re-overwritten with a brief build-complete summary (similar to the pattern used after the refactoring plan).
- Confirm all commits are on the `feature/policyiq-homepage` branch with correct `[Phase6.X]` messages.
- List any files not committed.
- Print a summary of what was built, all improvements made beyond the spec, and any deviations.
- Push the branch to remote.
- Do not open a pull request.
