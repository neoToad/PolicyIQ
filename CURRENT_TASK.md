# Current Task

**Step 3.5 — Citations Panel**

Adding the citations panel to PolicyIQ's query page.

- Added `#citations` div below `#answer` in `templates/queries/ask.html`
- JavaScript listens to `htmx:afterRequest`, reads `X-Citations` header, and renders a sources card
- Each citation shows document name, page number, similarity score as a percentage, and a 150-char preview
- Panel is hidden when no citations are present

Next: Phase 4 — Polish (4.1 Multi-Document Upload).