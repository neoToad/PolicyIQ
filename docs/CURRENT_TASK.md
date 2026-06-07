# Current Task

**Phase 0.2 in progress — building shared `ollama_client.py` (audit H4, L13, L20).**

## Status
- Branch `feature/policyiq-refactor` checked out from `main`
- Phase 0.1 fully complete (settings + per-module refactors for embedder, generator, chunker, retriever, views)
- 4 user decisions locked in:
  1. **Phase 2.2**: Drop `DocumentDeleteView`, staff-only deletes (matches default)
  2. **Phase 5.1**: **KEEP both** (PG `Chunk` model + ChromaDB text) — user override from default; document the rationale in `CLAUDE.md`
  3. **Phase 5.2**: Delete `queries/services/timing.py` and `queries/tests/test_timing.py` (matches default)
  4. **Phase 4.9**: **KEEP `test_views_pytest.py`, drop `test_views.py`** — user override from default; commit fully to pytest-style

## Currently working on
Phase 0.2 — building `policyiq/policyiq/ollama.py` shared client. This is the foundation for the refactor work in Phases 1–4: embedder, generator, health, and any other service that talks to Ollama will all funnel through one retry/envelope-detection layer.

## Next
- 0.2a: Write failing tests in `policyiq/tests/test_ollama_client.py` covering: post_json success/retry/exhaustion/HTTP error/error-envelope, post_stream success/midstream disconnect, validate_embedding_vector, ping true/false
- 0.2b: Implement `OllamaError`, `post_json`, `post_stream`, `is_error_envelope`, `validate_embedding_vector`, `ping`
- 0.2c: Migrate `embedder.py` (`_embed_batch_with_retry` / `_embed_single_with_retry` → `ollama_client.embed_texts` + per-text loop)
- 0.2d: Migrate `generator.py` (`_generate_ollama` → `ollama_client.generate(stream=True)`)
- 0.2e: Migrate `health.py` (`check_ollama` → `ollama_client.ping`)
- 0.3: Final verify (full pytest, manual smoke of upload + query + /healthz)

## After Phase 0
Phase 1 (pipeline atomicity, H1) — wraps `ingest_document` in `transaction.atomic`, swaps order to index-then-bulk_create, adds vector compensation.
