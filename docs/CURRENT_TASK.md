# Current Task

**Phase 0 COMPLETE — foundation in place. Moving to Phase 1 next.**

## Status
- Branch `feature/policyiq-refactor` checked out from `main`
- Phase 0 fully complete (settings + ollama_client + per-module migrations)
- 4 user decisions locked in:
  1. **Phase 2.2**: Drop `DocumentDeleteView`, staff-only deletes (matches default)
  2. **Phase 5.1**: **KEEP both** (PG `Chunk` model + ChromaDB text) — user override from default; document the rationale in `CLAUDE.md`
  3. **Phase 5.2**: Delete `queries/services/timing.py` and `queries/tests/test_timing.py` (matches default)
  4. **Phase 4.9**: **KEEP `test_views_pytest.py`, drop `test_views.py`** — user override from default; commit fully to pytest-style

## Phase 0 — done
- **0.1**: 16 env-overridable settings in `settings.py`; `policyiq.llm_config` URL helpers; per-module settings wiring for embedder/generator/chunker/retriever/views/similarity context processor
- **0.2**: `policyiq/ollama.py` shared client with `post_json`, `post_stream`, `embed_texts`, `embed_query`, `generate`, `ping`, `is_error_envelope`, `validate_embedding_vector`; `OllamaError` base with `EmbeddingError`/`GenerationError` aliases
- **0.2c/d/e**: embedder, generator, health now delegate to the shared client — one retry policy, one error-envelope contract
- **0.3**: Full suite green (215 tests), ruff clean, `manage.py check` clean, live smoke test of `/api/health/`, `/`, `/ask/`, `/upload/`, `/history/`, `/admin/` all return expected codes

## Next — Phase 1
Pipeline atomicity (audit H1) — wrap `ingest_document` in `transaction.atomic`, swap order to index-then-bulk_create, add vector compensation if the DB write fails after the index write.
