# Current Task

**Phase 0 in progress — Foundation: shared settings + shared Ollama client.**

## Status
- Branch `feature/policyiq-refactor` checked out from `main` (clean working tree aside from `docs/prompts/refactor_prompt.md` modification)
- Baseline: 143 tests pass on main
- 4 user decisions locked in:
  1. **Phase 2.2**: Drop `DocumentDeleteView`, staff-only deletes (matches default)
  2. **Phase 5.1**: **KEEP both** (PG `Chunk` model + ChromaDB text) — user override from default; document the rationale in `CLAUDE.md`
  3. **Phase 5.2**: Delete `queries/services/timing.py` and `queries/tests/test_timing.py` (matches default)
  4. **Phase 4.9**: **KEEP `test_views_pytest.py`, drop `test_views.py`** — user override from default; commit fully to pytest-style

## Currently working on
Phase 0.1a — adding new settings to `policyiq/policyiq/settings.py`:
- OLLAMA_EMBED_URL, OLLAMA_GENERATE_URL (derived from OLLAMA_BASE_URL via llm_config)
- OLLAMA_EMBED_MODEL, OLLAMA_GENERATE_MODEL
- ANTHROPIC_MODEL, ANTHROPIC_MAX_TOKENS
- EMBEDDING_RETRY_ATTEMPTS, EMBEDDING_RETRY_DELAY, EMBEDDING_BATCH_SIZE
- EMBEDDING_BATCH_TIMEOUT, EMBEDDING_QUERY_TIMEOUT, GENERATION_TIMEOUT
- CHUNK_SIZE, CHUNK_OVERLAP
- RETRIEVAL_TOP_K, SIMILARITY_THRESHOLD, SIMILARITY_BAR_HIGH
- PDF_MAX_BYTES

## Next
- 0.1b: Add `policyiq/services/llm_config.py` with `get_ollama_*_url()` helpers
- 0.1c–0.1g: Refactor embedder, generator, chunker, retriever, views to read from settings
- 0.1h: Context processor for `ask.html:69` JS threshold bar
- 0.2a–0.2d: Build `policyiq/policyiq/ollama.py` shared client; migrate embedder/generator/health
- 0.3: MEDIA_ROOT local-FS comment

## After Phase 0
Phase 1 (pipeline atomicity, H1) — wraps `ingest_document` in `transaction.atomic`, swaps order to index-then-bulk_create, adds vector compensation.
