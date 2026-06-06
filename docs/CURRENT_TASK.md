# Current Task

**Phase 6: Homepage build** — In progress, following `docs/homepage-plan.md` §2.8.

## Current step
**§2.8 step 5 — add `home.html` template.** Three sections: hero, how-it-works
(3 cards), library stats card. Uses `{% url 'upload-page' %}` and
`{% url 'ask-page' %}` for the CTAs, `{% url 'history-page' %}` for the
last-upload doc name link, and `{{ stats.last_upload.uploaded_at|timesince }}`
for the "3 hours ago" relative time.

## What's next
§2.8 step 6: CSS additions for `.hero`, `.hero-cta`, `.feature-grid`,
`.feature-card`, `.stat-grid`, `.stat`. Then pre-commit, full suite, and
final tracking-file updates.

## Branch
`feature/policyiq-homepage` (created from `main`).
