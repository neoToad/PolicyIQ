# Current Task

**Step**: Phase 5.3 — Add health check endpoint
**Status**: In progress
**What I'm working on**: Adding `/api/health/` endpoint that checks PostgreSQL (SELECT 1), ChromaDB (get_collection heartbeat), and Ollama (HTTP GET to /api/tags). Returns 200 with component status, or 503 if any dependency is down.

**Blockers/Decisions**: None

**Next step**: Implement health check view, commit 5.3, then proceed to Phase 5.4 (batch embedding requests).
