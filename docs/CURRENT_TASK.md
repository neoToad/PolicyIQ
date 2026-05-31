# Current Task

**Step**: 2.5 — Decouple `retriever.py` from `documents.models`
**Status**: Starting
**What I'm doing**: Removing the cross-app ORM dependency from `retriever.py` by storing `document_name` in ChromaDB metadata during indexing, so the retriever never needs to query PostgreSQL

**Blockers/Decisions**: None

**Next step**: 2.6 — Singleton ChromaDB client
