<!--
This file is one slice of the 6-phase refactor described in docs/prompts/refactor_prompt.md.
Commit format: <type>(<scope>): <summary> [PhaseN.X]. Read the prompt's Git Setup, TDD Rules, and Locked Decisions sections before starting.
-->

# Phase 6 — Verify, log, tag

After all five phases, do a final pass:

1. **Run the full test suite:** `pytest -x --cov`. Confirm coverage is non-decreasing and all tests pass.
2. **Manual smoke:** upload a PDF, run a query that hits the answer branch, run a query that hits the "no information" branch, run a query with Ollama down, hit `/healthz/`. Confirm logs are clean and not noisy.
3. **Update `docs/CHANGELOG.md`** with a single entry: `## Refactor pass — closes all findings in docs/REFACTOR_AUDIT.md` and a bullet list of phase summaries.
4. **Update `CLAUDE.md`** with the decision from Phase 5.1 (where chunks live) per Locked Decision #2.
5. **Tag the release.**
