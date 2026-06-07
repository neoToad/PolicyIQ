<!--
This file is one slice of the 6-phase refactor described in docs/prompts/refactor_prompt.md.
Commit format: <type>(<scope>): <summary> [PhaseN.X]. Read the prompt's Git Setup, TDD Rules, and Locked Decisions sections before starting.
-->

# Phase 0 — Foundation: shared settings + shared Ollama client (touch everything else) COMPLETED

**Why first:** The High finding "Hardcoded model names, URLs, and tunables" (audit H3) and the High finding "Duplicated Ollama HTTP call pattern" (audit H4) both touch 4–5 modules. Several later phases (H1, H5, H6, M1, M13, L9) consume the new client or the new settings, so building this first prevents rework.

### 0.1 Centralize settings (audit H3, L9, L13)

**Files touched:** `policyiq/policyiq/settings.py`, every service module, every view module, every test that referenced the old constants.

**New settings (with env-var defaults):**
- `OLLAMA_BASE_URL` = `os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")` (the existing setting — keep name, but actually use it).
- `OLLAMA_EMBED_URL` and `OLLAMA_GENERATE_URL` derived from `OLLAMA_BASE_URL` via a small helper in `policyiq/services/__init__.py` (or a top-level `policyiq/ollama.py` once it exists in 0.2).
- `OLLAMA_EMBED_MODEL` (default `"nomic-embed-text"`).
- `OLLAMA_GENERATE_MODEL` (default `"llama3.2"`).
- `ANTHROPIC_MODEL` (default `"claude-sonnet-4-20250514"`).
- `ANTHROPIC_MAX_TOKENS` (default `1024`).
- `EMBEDDING_RETRY_ATTEMPTS` (default `3`).
- `EMBEDDING_RETRY_DELAY` (default `1`).
- `EMBEDDING_BATCH_SIZE` (default `32`).
- `EMBEDDING_BATCH_TIMEOUT` (default `60`).
- `EMBEDDING_QUERY_TIMEOUT` (default `30`).
- `GENERATION_TIMEOUT` (default `60`).
- `CHUNK_SIZE` (default `500`).
- `CHUNK_OVERLAP` (default `50`).
- `RETRIEVAL_TOP_K` (default `5`).
- `SIMILARITY_THRESHOLD` (default `0.5`).
- `SIMILARITY_BAR_HIGH` (default `0.75`) — for the JS bar boundary in `templates/queries/ask.html:69`.
- `PDF_MAX_BYTES` (default `50 * 1024 * 1024`).
- `MEDIA_ROOT_ASSUMES_LOCAL_FS` comment near `MEDIA_ROOT` (audit L10).

**TDD steps:**
1. **Failing test:** `policyiq/tests/test_settings.py::test_required_settings_present` reads `getattr(settings, "OLLAMA_EMBED_MODEL", None)` and asserts the value. Add a new test that imports a helper `policyiq/services/llm_config.py::get_ollama_embed_url()` and asserts the URL is built from `OLLAMA_BASE_URL`. (Both fail because the helper and the settings don't exist yet.)
2. **Implement:** Add the settings entries, write the helper, export it.
3. **Refactor:** Replace every literal in `embedder.py`, `generator.py`, `chunker.py`, `retriever.py`, `views.py`, `health.py` with a `settings.X` read (or a helper) — one module at a time, keeping tests green between modules.
4. **Surface to template:** Add a context processor in `policyiq/documents/context_processors.py` (or `policyiq/policyiq/context_processors.py`) that injects `SIMILARITY_THRESHOLD` and `SIMILARITY_BAR_HIGH`. Update `templates/queries/ask.html:69` to read them.
5. **Verify:** `pytest -x policyiq` and a manual smoke for the JS bar.

**Commit cadence:** one `chore(settings):` for the new entries, then one `refactor(embedder): use settings.X` per module, then one `feat(templates): threshold from context`.

### 0.2 Build the shared `ollama_client.py` (audit H4, L13, L20)

**New file:** `policyiq/policyiq/ollama.py` (or `policyiq/services/ollama_client.py` if you prefer an app-shaped tree at the project root; pick one and stick with it — recommended: `policyiq/policyiq/ollama.py` because it's project-wide infrastructure, not a domain service).

**Public API:**
- `class OllamaError(Exception)` — base for `EmbeddingError` / `GenerationError` aliases.
- `post_json(path: str, payload: dict, *, timeout: float) -> dict` — single POST with the shared retry loop, returning parsed JSON or raising `OllamaError`. Uses `EMBEDDING_RETRY_ATTEMPTS` / `EMBEDDING_RETRY_DELAY` from settings.
- `post_stream(path: str, payload: dict, *, timeout: float) -> Iterator[dict]` — streaming variant for `/api/generate` that yields decoded JSON lines, raising `OllamaError` on transport failure.
- `embed_texts(model: str, texts: list[str]) -> list[list[float]]` — thin wrapper over `post_json("/api/embed", ...)`.
- `embed_query(model: str, text: str) -> list[float]` — thin wrapper over `post_json("/api/embed", ...)`.
- `generate(model: str, prompt: str, *, stream: bool) -> Iterator[str] | str` — thin wrapper that picks `post_stream` or `post_json("/api/generate", ...)` based on `stream`.
- `ping() -> bool` — uses `GET /api/tags` (audit L20).
- `is_error_envelope(data: dict) -> bool` — detects `{"error": "..."}` from Ollama 200 responses (audit M8).
- `validate_embedding_vector(vec: list) -> list[float]` — checks each element is a number (audit M8).

**TDD steps:**
1. **Failing tests** in `policyiq/tests/test_ollama_client.py`:
   - `test_post_json_returns_parsed_dict` — patches `requests.post` to return `Mock(json=lambda: {"ok": True}, raise_for_status=lambda: None)`.
   - `test_post_json_retries_on_request_exception` — patches `requests.post` to raise twice then succeed; asserts 3 calls.
   - `test_post_json_raises_ollama_error_after_max_attempts` — patches to always raise; asserts `OllamaError`.
   - `test_post_json_raises_on_http_error_status` — patches to return 500 with `raise_for_status` that raises.
   - `test_post_json_raises_on_error_envelope` — patches to return 200 with `{"error": "model not found"}`; asserts `OllamaError` and message contains `"model not found"`.
   - `test_post_stream_yields_decoded_lines` — patches `iter_lines` to yield 3 JSON lines; asserts the iterator yields 3 dicts.
   - `test_post_stream_raises_on_midstream_disconnect` — patches `iter_lines` to yield 2 lines then raise `ChunkedEncodingError`; asserts `OllamaError` (this is also the H7 / M10 test in a different home).
   - `test_validate_embedding_vector_rejects_strings` — asserts `TypeError` (or `OllamaError`) on a `["a", "b"]` input.
   - `test_ping_returns_true_on_200` and `test_ping_returns_false_on_connection_error`.
2. **Implement** the client. Keep it small and dependency-free.
3. **Migrate** `embedder.py` and `generator.py` to call into the client. Delete the local `_embed_batch_with_retry` / `_embed_single_with_retry` / `_generate_ollama` HTTP code. The only thing left in `embedder.py` should be: shape normalization, batching, and the `embed_chunks` / `embed_query` public entry points.
4. **Verify** all existing tests in `policyiq/documents/tests/test_services.py` and `policyiq/queries/tests/test_services.py` / `test_generator.py` still pass with no changes (or with minimal mock-patch updates if the mock targets changed).

**Commit cadence:** `feat(infra): add ollama_client with retry and error-envelope detection`, then `refactor(embedder): use shared ollama_client`, then `refactor(generator): use shared ollama_client`, then `refactor(health): use shared ollama_client.ping`.

### 0.3 Verify Phase 0

Run `pytest -x` and a manual smoke (upload a PDF, run a query, hit `/healthz/`). If green, tag the commit and move on.
