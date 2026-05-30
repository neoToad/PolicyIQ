# Current Task

**Step 4.3 — Admin Delete and Re-index**

Building a staff-only admin view for document management.

- Create `/admin/documents/` view protected by `@staff_member_required`
- List all documents with metadata, delete buttons, and re-index buttons
- Delete removes from both PostgreSQL and ChromaDB
- Re-index re-runs the full pipeline on the stored PDF and updates chunk counts
- Writing tests first per TDD workflow

Next: 4.4 — LLM Config Swap.
