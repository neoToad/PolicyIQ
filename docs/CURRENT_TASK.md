# Current Task

**Phase 6: Homepage build** — In progress, following `docs/homepage-plan.md` §2.8.

## Current step
**§2.8 step 4 — wire homepage URL at `/`.** Adding `path("", HomePageView.as_view(), name="home")`
to `policyiq/urls.py` so the `GET /` 404 turns into a 200 (or — more likely at this
point — a `TemplateDoesNotExist: home.html` since the template still doesn't exist).

## What's next
§2.8 step 5: add `templates/home.html` (the missing template). Step 6: CSS.
Step 7: pre-commit. Step 8: full suite green at 102. Step 9: tracking files.

## Branch
`feature/policyiq-homepage` (created from `main`).
