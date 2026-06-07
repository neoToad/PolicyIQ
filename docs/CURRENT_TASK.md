# Current Task

**Phase 0.2 in progress — building shared `ollama_client.py` (audit H4, L13, L20).**

## Status
- Branch `feature/policyiq-refactor` checked out from `main`
- Phase 0.1 fully complete (settings + per-module refactors for embedder, generator, chunker, retriever, views, plus similarity context processor)
- 4 user decisions locked in:
  1. **Phase 2.2**: Drop `DocumentDeleteView`, staff-only deletes (matches default)
  2. **Phase 5.1**: **KEEP both** (PG `Chunk` model + ChromaDB text) — user override from default; document the rationale in `CLAUDE.md`
  3. **Phase 5.2**: Delete `queries/services/timing.py` and `queries/tests/test_timing.py` (matches default)
  4. **Phase 4.9**: **KEEP `test_views_pytest.py`, drop `test_views.py`** — user override from default; commit fully to pytest-style

## Currently working on
Phase 0.2a — writing the failing tests for the shared Ollama client in `policyiq/tests/test_ollama_client.py`. The client will consolidate the duplicated `requests.post(...)` + retry/backoff pattern that today lives in `embedder.py::_embed_batch_with_retry` / `_embed_single_with_retry` and `generator.py::_generate_ollama` (audit H4).

The spec calls for these public functions (audit L20 for `ping` /api/tags, audit M8 for error-envelope detection):
- `post_json(path, payload, *, timeout)` — POST with shared retry loop, returns parsed dict or raises `OllamaError`
- `post_stream(path, payload, *, timeout)` — streaming variant for `/api/generate`, yields decoded JSON lines
- `embed_texts(model, texts)`, `embed_query(model, text)`, `generate(model, prompt, *, stream)` — thin wrappers
- `ping()` — `GET /api/tags` health probe
- `is_error_envelope(data)`, `validate_embedding_vector(vec)` — error-shape detectors

## Next
- 0.2b: Implement the client module
- 0.2c: Migrate `embedder.py` — drop `_embed_batch_with_retry` / `_embed_single_with_retry` in favor of `ollama_client.embed_texts` / `embed_query`
- 0.2d: Migrate `generator.py::_generate_ollama` → `ollama_client.generate(stream=True)`
- 0.2e: Migrate `health.py::check_ollama` → `ollama_client.ping`
- 0.3: Final verify (full pytest, manual smoke of upload + query + /healthz)

## After Phase 0
Phase 1 (pipeline atomicity, H1) — wraps `ingest_document` in `transaction.atomic`, swaps order to index-then-bulk_create, adds vector compensation.
