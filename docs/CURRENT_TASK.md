# Current Task

**Step**: 2.6 — Singleton ChromaDB client
**Status**: Starting
**What I'm doing**: Caching the ChromaDB `PersistentClient` instance so it is created lazily on first access and reused across calls, preventing locking issues under concurrency

**Blockers/Decisions**: None

**Next step**: 3.1 — Consolidate requirements.txt
