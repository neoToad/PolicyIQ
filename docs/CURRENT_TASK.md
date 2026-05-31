# Current Task

**Step**: Phase 4.5 — Add integration test scaffolding
**Status**: In progress
**What I'm working on**: Creating a `tests/integration/` directory with a basic ingestion + query round-trip test using Django `TestCase` and a test database. Marking with `@pytest.mark.integration` or Django test tags so they can be skipped in fast runs.

**Blockers/Decisions**: None

**Next step**: Commit 4.5, then proceed to Phase 4.6 (pytest migration).
