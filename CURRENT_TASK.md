# Current Task

**Step 3.3 — Upload History**

Building the upload history view for PolicyIQ.

- Updating `HistoryPageView` to fetch all documents and render `templates/documents/history.html`
- Adding `DocumentDeleteView` to remove documents from PostgreSQL and ChromaDB
- Wiring delete URL at `/documents/<uuid>/delete/`
- Table with HTMX delete buttons that remove the row on success

Next: 3.4 — Question Input.