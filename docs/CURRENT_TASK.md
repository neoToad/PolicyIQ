# Current Task

**Step**: Phase 5.3 — Add health check endpoint (committing)
**Status**: In progress — view + tests wired up, preparing to commit
**What I'm working on**: Health check endpoint that checks PostgreSQL, ChromaDB, and Ollama. Created `queries/services/health.py` with `check_postgresql`, `check_chromadb`, `check_ollama` helpers and a `HealthCheckAPIView` aggregating them. Wired up at `/api/health/`. Tests cover all-healthy, partial-down, all-down, and unauthenticated access.

**Blockers/Decisions**: Decided to extract a `health` service module (rather than inlining logic in the view) for cleaner testing and DRY — each check is independently testable and the view is reduced to a 5-line aggregation.

**Next step**: Commit Phase 5.3, push, then proceed to Phase 5.4 (batch embedding requests).