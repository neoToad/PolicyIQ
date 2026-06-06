# Current Task

**Step**: Phase 5.6 — Add pre-commit hooks
**Status**: Starting implementation

## Plan
- Add `.pre-commit-config.yaml` with hooks for:
  - `ruff check --fix` (lint)
  - `ruff format` (format)
  - Trailing whitespace
  - End-of-file fixer
  - YAML check
  - Large file check
- Add `pre-commit` to requirements.txt dev deps
- Create a simple `.pre-commit-hooks.yaml` (only needed if shipping as a hook package — not needed for consumer use)
- Optionally add a `Makefile` target that runs pre-commit and tests
- Add documentation in CHANGELOG
- The spec says "Add a pre-commit hook that runs the test suite (or at least lint)" — will go with lint+format (test suite is too slow for pre-commit)
- Verify `pre-commit` is installed and hooks run

## Next step on resume
1. Write `.pre-commit-config.yaml`
2. Update `requirements.txt` to add `pre-commit`
3. Add a `make lint` Makefile target (or document commands)
4. Run `pre-commit install` and `pre-commit run --all-files` to validate
5. Update CHANGELOG and commit as `[Phase5.6]`
6. After Phase 5.6: update the refactoring-plan.md status, mark ALL phases complete
