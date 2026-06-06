# Current Task

**Phase 6: Homepage build** — In progress, following `docs/homepage-plan.md` §2.8.

## Current step
**§2.8 step 3 — green phase for view.** Implementing `HomePageView` in
`documents/views.py` so the 3 view tests in `HomePageViewTests` pass. The
view must import `get_library_stats`, render `home.html`, and pass
`{"stats": ...}` to the template context.

## What's next
§2.8 step 4: wire the `path("", ...)` URL in `policyiq/urls.py` so `GET /`
actually returns 200. Step 5: add the `home.html` template. Step 6: CSS.

## Branch
`feature/policyiq-homepage` (created from `main`).
