# Current Task

**Phase 6: Homepage build** — In progress, following `docs/homepage-plan.md` §2.8.

## Current step
**§2.8 step 1 — TDD red phase.** Writing the failing tests:
- `documents/tests/test_stats.py` (4 tests for `get_library_stats()`)
- `HomePageViewTests` in `documents/tests/test_views.py` (3 tests for the new view)

Then I will run the suite and confirm the tests fail for the *right* reasons
(import error for `documents.services.stats`, view not found at `name="home"`,
`HomePageView` not defined, `home.html` template not found).

## What's next
§2.8 step 2: implement `documents/services/stats.py` until the 4 stats tests pass.

## Branch
`feature/policyiq-homepage` (created from `main`).
