# Claude Instructions

Before doing anything else, read `AGENTS.md` in this directory and follow all instructions found there.

---

## `Chunk` storage: kept in both PostgreSQL and ChromaDB (intentional)

PolicyIQ stores each chunk **twice** — once in the `documents_chunk`
PostgreSQL table and once in ChromaDB's `documents` field. This is
deliberate, not a bug, and was decided in the Phase 5.1 review of the
refactor audit (Locked Decision #2):

- The **PG `Chunk` row** is the source of truth for the relational
  metadata: `page_number`, `token_offset`, and the foreign key to
  `Document`. The Django admin and the reindex path both rely on
  these indexed columns (`Chunk.objects.filter(document=...)`,
  `select_related`, etc.). PG lookups on these columns are O(log n)
  and small per row.
- The **ChromaDB payload** holds the raw chunk text for vector
  retrieval. The retriever reads `text` directly from the ChromaDB
  response (`queries/services/retriever.py:85`) and never round-trips
  through PostgreSQL. The text is opaque to PG queries anyway.

Cost of duplication: one extra write per chunk per ingest. The
benefit: relational queries on chunk metadata stay fast, and the
vector store stays the single read path for semantic search. Sweep
for drift in a Phase 5 follow-up if it ever shows up — the two
stores can diverge if a reindex partially fails, and the audit
flagged the `Chunk.objects.filter(document=...).delete()` in the
reindex path as a "best-effort" pre-purge for exactly this reason.

Do **not** drop the `text` column from `Chunk` or move it to a
secondary table without revisiting this decision and the
`delete_document_with_chunks` ordering in
`documents/services/deletion.py`.
