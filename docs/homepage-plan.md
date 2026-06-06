# Homepage Plan

> **Status:** Analysis & proposal — no code changes yet. Awaiting approval before implementation.
> **Audience for the homepage:** Visitors (public) — first-time users who land on `/` and need to understand what PolicyIQ does before uploading or asking.
> **Implementation depth:** View + template + tests + small `stats` service module (so the view stays thin and stats are independently testable).
> **Stats visibility:** Visible to anonymous visitors. Aggregate, non-sensitive data, and reinforces the "library is alive" message. No `{% if user.is_authenticated %}` gate.
> **Last-upload subtitle:** "Last upload: <doc name>, <relative time ago>" with the document name linking to `/history/`. Falls back to "No documents uploaded yet — the library is empty." when the library is empty.

---

## 1. Analysis: What's Happening Now

### 1.1 The current root URL state

There is **no view, template, or URL pattern** for `/` (the homepage). Concretely:

- `policyiq/policyiq/urls.py` (lines 15–27) defines routes for `/admin/`, `/admin/documents/`, `/api/...`, `/upload/`, `/history/`, `/ask/`, and `/documents/<uuid>/delete/`. There is **no `path("", ...)` or `path("/", ...)` entry**.
- Hitting `http://localhost:8000/` in Django with `DEBUG=True` returns the default Django "Page not found" debug page; in production it returns a generic 404.
- The brand link in the nav already assumes `/` exists: `base.html:21` → `<a class="brand" href="/">PolicyIQ</a>`. Clicking the brand from any page currently 404s.

So a homepage is a real missing feature, not a polish task. The brand link is the only thing pointing at it.

### 1.2 The four pages that exist today

All four extend `base.html`, which provides the shared `<header>`/`<nav>` and a `<main class="container">` content slot.

| Page | URL | View | What it does |
|---|---|---|---|
| Upload | `/upload/` | `UploadPageView` (Django `View`) | HTMX form to upload one or more PDFs. Validates, ingests, returns inline result. |
| Ask | `/ask/` | `AskPageView` (Django `View`) | HTMX form with a question textarea + optional document dropdown. Streams answer with citations. |
| History | `/history/` | `HistoryPageView` (Django `View`) | Table of all uploaded documents with page count, chunk count, upload time, delete button. |
| Admin | `/admin/documents/` | `StaffDocumentListView` (`@staff_member_required`) | Same table as History, but with Re-index and Delete buttons. Staff-only. |

There are no landing pages, no marketing copy, no overview of what the app does, no library stats, no on-ramp for new users.

### 1.3 What the user sees when they first hit the app

1. They go to `http://localhost:8000/` → **404**.
2. If they guess the right URL and go to `/upload/`, they're dropped straight into a file-picker with a one-line description ("Select a PDF to ingest into the knowledge base") and no context about what just happened to their file or why it matters.
3. If they go to `/ask/`, they're asked a question before they've uploaded anything, and the page silently returns "I don't know" because there are no chunks in ChromaDB.
4. There is no obvious next step, no demo flow, and no "this is what PolicyIQ is" page anywhere.

### 1.4 What exists that we can reuse

- **README.md** is well-written and contains exactly the marketing copy a homepage needs: "No more ctrl-F through a 50-page Aetna policy", the "Why RAG?" four-bullet argument, the architecture diagram, and the tech-stack table. The homepage should *quote* the README, not duplicate its engineering detail.
- **CSS design system** lives in `static/css/main.css`: CSS variables (`--accent`, `--surface`, etc.), `.card`, `.btn`, `.container`, `.text-secondary`, `.mt-4`, `.mb-2`, table styles, form styles. We can compose a homepage from these primitives without adding new visual language.
- **`Document` model** has `page_count`, `chunk_count`, `uploaded_at`, `name`. All the inputs we need for a library-stats block are already aggregated columns on the model — no schema changes, no migrations.
- **`Aggregate()` queries** are supported by the existing Postgres-backed ORM. `Document.objects.aggregate(total=Sum("chunk_count"))` is one line.
- **The nav already adapts** to `user.is_staff` (`base.html:26-28`), so the homepage can lean on the same `{% if user.is_staff %}` pattern if we ever want a staff-only stats panel.

### 1.5 Constraints / things to respect

- **HTMX-first architecture** — no JS framework, no build step. The homepage is server-rendered HTML. (Per Phase 3 of `refactoring-plan.md`: "Don't add a JavaScript framework — the HTMX architecture is a deliberate choice.")
- **Django `View` for pages, `APIView` for JSON** — match the existing convention in `documents/views.py` and `queries/views.py`.
- **Tests live next to the view** — `documents/tests/test_views.py` already follows the `XxxViewTests(TestCase)` pattern. New homepage tests slot in there.
- **AGENTS.md TDD rule** — for new features, write failing tests first, confirm they fail for the right reasons, then write minimum code to pass.
- **No schema changes** — we agreed not to add a `QueryLog` model for this round, so the homepage stats are derived from existing `Document` / `Chunk` rows.

---

## 2. The Plan

### 2.1 Goals

1. Replace the 404 on `/` with a real, on-brand landing page.
2. Make the brand link in the nav (`base.html:21`) work.
3. Show visitors (1) what PolicyIQ is, (2) how it works at a high level, and (3) a quick "is this thing alive?" check via library stats.
4. Drive visitors to either Upload or Ask with two clear CTAs.
5. Keep the view thin — push the stats math into a small, independently testable service module.

### 2.2 What goes on the page

Three sections, top to bottom:

1. **Hero** — one-line tagline + one-paragraph value prop + two CTA buttons (Upload / Ask).
   - Tagline: "Ask plain-language questions about payer policy PDFs."
   - Body: a 2–3 sentence paraphrase of README "The Problem" / "Why RAG?" — focused on *outcome* (no more ctrl-F), not architecture.
2. **How it works** — a 3-step feature walkthrough rendered as three cards:
   - **Upload** your payer policy PDFs.
   - **Ask** a question in plain language.
   - **Get an answer** with citations to the source page.
   Each card has a small icon-free description and a "Learn more →" link that deep-links to the corresponding page.
3. **Library stats** — a single `.card` with a "last upload" line (doc name + relative time, or empty-state message) plus three numbers: total documents, total chunks indexed, total pages. Driven by a new `documents/services/stats.py` module so the view stays a 5-line aggregator and the math is unit-testable without going through a request. Stats are visible to anonymous visitors.

(No "recent documents" or "recent queries" block — deferred per the question-answers. A `QueryLog` model would be a separate, larger feature.)

### 2.3 Files to add / change

| File | Change | Why |
|---|---|---|
| `policyiq/documents/services/stats.py` | **New.** `get_library_stats() -> dict[str, int]` returning `{documents, chunks, pages}`. | Keep the view thin; let tests assert the math directly. |
| `policyiq/documents/tests/test_stats.py` | **New.** Unit tests for `get_library_stats()`. | AGENTS.md: tests for service modules. |
| `policyiq/documents/views.py` | **Add** `HomePageView` (Django `View`) with a `get()` that calls `get_library_stats()` and renders `home.html`. | Match the existing `View` pattern (`UploadPageView`, `HistoryPageView`). |
| `policyiq/documents/tests/test_views.py` | **Add** `HomePageViewTests` — `test_get_renders_homepage`, `test_get_uses_service_for_stats`, `test_get_passes_stats_to_template`. | AGENTS.md: `test_views.py` for view tests. |
| `policyiq/templates/home.html` | **New.** Extends `base.html`, three sections (hero / how-it-works / stats). | Single new template; uses existing CSS classes. |
| `policyiq/policyiq/urls.py` | **Add** `path("", HomePageView.as_view(), name="home")`. | Wires up the new view to `/`. |
| `policyiq/static/css/main.css` | **Small additions** (≤30 lines): `.hero`, `.feature-grid`, `.feature-card`, `.stat-grid`, `.stat`. | Composes the new page from existing design tokens. No new colors, no new fonts. |
| `docs/CHANGELOG.md` | **Append** a `[Phase6.x]` (or similar) entry following the existing format. | Matches the established changelog convention. |
| `docs/CURRENT_TASK.md` | **Update** to point at the new homepage work, then back to "None" when done. | Matches the established tracking convention. |

**No changes to:** `models.py`, `migrations/`, `services/pipeline.py`, `services/indexer.py`, `services/embedder.py`, `services/extractor.py`, `services/chunker.py`, `queries/*`, `requirements.txt`, `pyproject.toml`, `.pre-commit-config.yaml`.

### 2.4 URL and view sketch

```python
# policyiq/policyiq/urls.py (add to urlpatterns)
path("", HomePageView.as_view(), name="home"),
```

```python
# policyiq/documents/views.py
class HomePageView(View):
    """Public landing page: explains what PolicyIQ is and shows library stats."""

    def get(self, request: HttpRequest) -> HttpResponse:
        """Render the homepage with hero, how-it-works, and library stats."""
        stats = get_library_stats()
        return render(request, "home.html", {"stats": stats})
```

```python
# policyiq/documents/services/stats.py
from django.db.models import Sum

from documents.models import Document


def get_library_stats() -> dict:
    """Return aggregate stats across all documents in the knowledge base.

    Returns:
        A dict with keys:
          - documents (int): non-negative count of documents
          - chunks (int): total chunk_count across all documents
          - pages (int): total page_count across all documents
          - last_upload (dict | None): {id, name, uploaded_at} for the most
            recently uploaded document, or None if the library is empty
        Empty-library callers get all-zero ints and last_upload=None.
    """
    aggregate = Document.objects.aggregate(
        documents=Count("id"),
        chunks=Sum("chunk_count"),
        pages=Sum("page_count"),
    )
    last = (
        Document.objects.order_by("-uploaded_at")
        .values("id", "name", "uploaded_at")
        .first()
    )
    return {
        "documents": aggregate["documents"] or 0,
        "chunks": aggregate["chunks"] or 0,
        "pages": aggregate["pages"] or 0,
        "last_upload": last,
    }
```

### 2.5 Template sketch

```html
{% extends "base.html" %}
{% block title %}PolicyIQ – Ask questions of your payer policy PDFs{% endblock %}

{% block content %}
  <section class="hero">
    <h1>Ask plain-language questions about payer policy PDFs.</h1>
    <p class="text-secondary">
      No more ctrl-F through a 50-page Aetna policy. Upload your payer's policy documents,
      ask in plain language, and get a grounded answer with citations showing exactly
      where in the document it came from.
    </p>
    <div class="hero-cta">
      <a class="btn" href="{% url 'upload-page' %}">Upload a PDF</a>
      <a class="btn btn-secondary" href="{% url 'ask-page' %}">Ask a question</a>
    </div>
  </section>

  <section class="feature-grid mt-4">
    <div class="feature-card card">
      <h3>1. Upload</h3>
      <p>Drop in your payer policy PDFs. We extract, clean, chunk, and index them locally.</p>
      <a href="{% url 'upload-page' %}">Go to Upload →</a>
    </div>
    <div class="feature-card card">
      <h3>2. Ask</h3>
      <p>Type a question the way you'd ask a coworker. Optionally scope it to a single document.</p>
      <a href="{% url 'ask-page' %}">Go to Ask →</a>
    </div>
    <div class="feature-card card">
      <h3>3. Get a cited answer</h3>
      <p>A grounded response with source document, page number, and the exact passage used.</p>
    </div>
  </section>

  <section class="card mt-4">
    <h3>The library so far</h3>
    {% if stats.last_upload %}
      <p class="text-secondary text-sm">
        Last upload: <a href="{% url 'history-page' %}">{{ stats.last_upload.name }}</a>, {{ stats.last_upload.uploaded_at|timesince }} ago.
      </p>
    {% else %}
      <p class="text-secondary text-sm">No documents uploaded yet — the library is empty.</p>
    {% endif %}
    <div class="stat-grid">
      <div class="stat"><span class="stat-num">{{ stats.documents }}</span><span class="stat-label">documents</span></div>
      <div class="stat"><span class="stat-num">{{ stats.chunks }}</span><span class="stat-label">chunks indexed</span></div>
      <div class="stat"><span class="stat-num">{{ stats.pages }}</span><span class="stat-label">pages of policy</span></div>
    </div>
  </section>
{% endblock %}
```

### 2.6 CSS additions (≤30 lines)

```css
.hero { padding: 32px 0; }
.hero h1 { font-size: 2.25rem; max-width: 720px; }
.hero p { max-width: 640px; font-size: 1.05rem; }
.hero-cta { display: flex; gap: 12px; margin-top: 20px; }
.btn-secondary { background: var(--surface); color: var(--accent); border: 1px solid var(--border); }
.btn-secondary:hover { background: var(--bg); }

.feature-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
@media (max-width: 720px) { .feature-grid { grid-template-columns: 1fr; } }
.feature-card a { color: var(--accent); text-decoration: none; font-weight: 500; }
.feature-card a:hover { text-decoration: underline; }

.stat-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-top: 12px; }
.stat { display: flex; flex-direction: column; align-items: flex-start; }
.stat-num { font-size: 2rem; font-weight: 700; color: var(--text); }
.stat-label { font-size: 0.85rem; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.04em; }
```

### 2.7 Test plan

**Unit (no DB, fully mocked):**
- `documents/tests/test_stats.py`:
  - `test_get_library_stats_empty_db_returns_zeros` — patch `Document.objects.aggregate` to return `{documents: 0, chunks: None, pages: None}` and the last-upload lookup to return `None`; assert the function coerces `None` to `0` and `last_upload` is `None`.
  - `test_get_library_stats_passes_through_counts` — patch aggregate to return `{documents: 7, chunks: 1234, pages: 567}`; assert the int dict matches.
  - `test_get_library_stats_returns_last_upload_dict` — patch the latest-uploads lookup to return `{"id": uuid, "name": "Aetna-2026-Policy.pdf", "uploaded_at": <datetime>}`; assert `last_upload` matches.
  - `test_get_library_stats_last_upload_none_when_empty` — explicit empty-library assertion (overlaps #1 but called out separately to make the contract obvious).

**View (Django `TestCase`, in-memory SQLite):**
- `documents/tests/test_views.py::HomePageViewTests`:
  - `test_get_renders_home_template` — GET `/` returns 200, uses `home.html`, contains the hero H1 text.
  - `test_get_calls_stats_service` — assert `get_library_stats` is called exactly once.
  - `test_get_passes_stats_to_template` — assert the rendered HTML contains the stat numbers.
  - `test_get_does_not_require_authentication` — anonymous GET still returns 200 (per "Visitors (public)" audience choice; stats are visible to anonymous users per the agreed visibility policy).
  - `test_get_renders_last_upload_line_with_link_when_present` — fixture creates one Document with a known name and `uploaded_at`; assert the rendered HTML contains the doc name as a link to `/history/`.
  - `test_get_renders_empty_library_message_when_no_documents` — no Documents in the DB; assert the rendered HTML contains the "No documents uploaded yet" message and the stats still render as 0.

### 2.8 Implementation order (TDD per AGENTS.md)

1. Write `documents/tests/test_stats.py` and `HomePageViewTests` — run, confirm they fail for the right reasons (import errors / template not found / view returns 404). The view tests for "last upload" use a `Document` fixture (so they need to live in `TestCase`, not `SimpleTestCase` — which the homepage test class will be anyway).
2. Implement `documents/services/stats.py` until `test_stats.py` passes (including the `last_upload` dict shape).
3. Implement `HomePageView` in `documents/views.py` until the view tests pass.
4. Add the `path("", ...)` URL — the 404 test should now pass.
5. Create `templates/home.html` — the template-not-found test should now pass.
6. Add the CSS — visual verification (open in browser, confirm hero / cards / stats render).
7. Run `pre-commit run --all-files` — should be clean.
8. Run full test suite — should be 99 tests (95 + 4 new) all green.
9. Update `docs/CHANGELOG.md` and `docs/CURRENT_TASK.md`.
10. Commit as `[Phase6.1] Add public homepage with hero, feature walkthrough, and library stats`.

### 2.9 Out of scope (deliberately)

- A "Recent documents" / "Recent queries" block on the homepage — requires a `QueryLog` model + migration; not worth the schema cost for v1.
- A search box on the homepage — `AskPageView` is one click away; a second search input would be redundant.
- Authentication or session-aware content — visitors see the same page as logged-in users (the "Visitors (public)" audience choice). If we later want an adaptive page, that's a separate task.
- A "Try a sample query" interactive demo on the homepage — would require seeding sample documents; not in scope.
- Any rewrite of the existing four pages — they stay as-is.

### 2.10 Risks and open questions

- **Risk:** `Sum()` returns `None` (not `0`) on an empty table, so the `or 0` coercion is required. The test for that case is explicit. Low risk, but easy to miss in a refactor later.
- **Risk:** Adding a new URL to `policyiq/urls.py` at `path("", ...)` could shadow the static-file serving or the admin catch-all. Mitigation: `path("", ...)` is added *before* the admin catch-all and the static-file serving is gated by `settings.DEBUG`, so there is no shadowing.
- **Resolved:** Stats are visible to anonymous visitors (no `{% if user.is_authenticated %}` gate).
- **Resolved:** Last-upload line is included on the stats card, with the document name + relative time + link to `/history/`.
- **Resolved:** Subtitle uses Django's `|timesince` filter (relative form: "3 hours ago") — feels alive and matches the "library is alive" message better than an absolute timestamp.

---

## 3. Alternatives Considered

| Alternative | Why not chosen |
|---|---|
| Redirect `/` to `/upload/` | Hides the value prop; the user asked for an actual homepage, and the brand link should land on something other than the upload form. |
| Make the homepage a static `.html` in `public/` (WhiteNoise-style) | The library stats need to be dynamic; a static file can't show "7 documents, 1,234 chunks." Django-rendered is the right fit. |
| Add a "Recent documents" block | Requires a new template fragment that re-uses `HistoryPageView`'s logic; deferred to keep the scope tight. |
| Add a `QueryLog` model and a "Recent questions" block | Out of scope per the depth-of-implementation answer; would also require a migration, an admin registration, and possibly retention policy. |
| Render the homepage with the `AskPageView` template at `/` | `ask.html` is a form, not a landing page. The two views serve different purposes; conflating them would muddy both. |
| Use a single hero CTA that adapts ("Get started" → Upload if empty, Ask if not) | Rejected in favor of showing both Upload and Ask as equally prominent, since both are first-class entry points. |
| Add JS for animated counters on the stats | Vanilla CSS / a one-line `style="--n:7"` trick can do this without JS, but it's nice-to-have, not required. Defer. |
| Build a separate "marketing site" (e.g., a Next.js app) | Explicitly out of scope per the refactoring plan's "Don't add a JavaScript framework" rule. |
| Put the feature walkthrough on a separate `/about/` page | Discoverability suffers; the user lands on `/` and needs the explanation right there. |
| Add the homepage as a CMS-managed Markdown page | Premature; we have no CMS, no editors, and no need for one. A Django template is the right tool for the next 12 months. |

---

## 4. Acceptance Criteria

The work is "done" when **all** of the following are true:

1. `GET /` returns HTTP 200 with a server-rendered HTML page.
2. The page contains: a hero with a tagline and two CTAs, a three-card "How it works" section, and a stats card with three numbers.
3. The brand link in the nav (`base.html:21`) lands on `/` and the page renders.
4. The two CTA buttons link to `/upload/` and `/ask/` respectively.
5. The stats are computed by `documents.services.stats.get_library_stats()` — not inline in the view.
6. `documents/tests/test_stats.py` exists and passes.
7. `HomePageViewTests` exists in `documents/tests/test_views.py` and passes.
8. The full test suite is green (102 tests: 95 existing + 7 new: 4 service + 3 view).
9. `ruff check policyiq/` and `ruff format --check policyiq/` are clean.
10. `pre-commit run --all-files` is clean.
11. `docs/CHANGELOG.md` has a new entry for this work; `docs/CURRENT_TASK.md` is updated to "Next step: None" once the build is complete.
12. No schema changes, no new dependencies, no new apps.

---

## 5. Estimated Effort

| Task | Estimate |
|---|---|
| Tests (TDD red phase) | 15 min |
| `stats.py` service | 10 min |
| `HomePageView` | 5 min |
| `home.html` template | 20 min |
| CSS additions | 10 min |
| URL wiring | 2 min |
| Changelog + current-task updates | 5 min |
| `pre-commit run --all-files` + full test run | 5 min |
| **Total** | **~70 min** |

---

## 6. Next Step

**Awaiting approval on this plan.** Once approved, I'll execute it in the TDD order laid out in §2.8. If you'd like to change scope (e.g., drop the library-stats block, or add the recent-documents block after all), say the word and I'll revise the plan before touching code.
