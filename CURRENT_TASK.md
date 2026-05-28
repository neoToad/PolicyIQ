# Current Task

**Step 3.4 — Question Input**

Building the question input template and ask view for PolicyIQ.

- Updating `AskPageView` to handle GET (with documents dropdown) and POST (query pipeline)
- Rewriting `templates/queries/ask.html` with HTMX form: textarea, document selector, loading indicator
- POST returns HTML partials or a StreamingHttpResponse with HTML-wrapped tokens
- Preserves X-Citations header for the citations panel in step 3.5

Next: 3.5 — Citations Panel.