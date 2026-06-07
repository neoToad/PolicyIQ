<!--
This file is one slice of the 6-phase refactor described in docs/prompts/refactor_prompt.md.
Commit format: <type>(<scope>): <summary> [PhaseN.X]. Read the prompt's Git Setup, TDD Rules, and Locked Decisions sections before starting.
-->

# Phase 5 — Cleanup, dead code, and consistency (audit M1, M4, M5, M6, M13, L2, L5, L6, L10, L12, L14, L15, L16, L17, L18, L19, L20, L21)

**Why sixth:** The remaining items don't block correctness; they reduce noise and risk. Order them so each commit is small and reviewable.

### 5.1 Decide on `Chunk` storage duplication (audit M1)

**Per Locked Decision #2 in `../refactor_prompt.md`, keep both** — the PG `Chunk` model AND the ChromaDB text payloads. Document the rationale in `CLAUDE.md` (this is the only Phase 5.1 deliverable; no migration, no field removal).

Suggested `CLAUDE.md` note (one short paragraph): the relational `Chunk` model is the source of truth for `page_number` / `token_offset` / `document_id` joins used by admin views, reindex purges, and citation lookups; ChromaDB holds the raw text for vector retrieval. Keeping them duplicated is intentional — the relational row is small, indexed, and cheap to keep in sync, while ChromaDB payloads are opaque to PG queries. Sweep for drift in the Phase 5 follow-up if it ever shows up.

### 5.2 Drop `StageTimer` / `timing.py` (audit M4)

**Per Locked Decision #3 in `../refactor_prompt.md`, delete** `queries/services/timing.py` and `queries/tests/test_timing.py`. Add a `# TODO: shared stage timer` comment at each inline `t0 = time.monotonic()` block in the five services that have them.

**Commit:** `chore(queries): drop unused stage_timer`.

### 5.3 Drop leading underscores on `_generate_ollama` / `_generate_anthropic` (audit M6)

After Phase 0.2, the HTTP code lives in `ollama.py`. The wrappers in `generator.py` can be renamed `generate_ollama` / `generate_anthropic` and the existing test can be re-routed through the public `generate_response` with `LLM_BACKEND=anthropic`.

**Commit:** `refactor(generator): drop private-name wrappers, route tests through public dispatch`.

### 5.4 Replace `_STAGE_BY_EXCEPTION_NAME` with `isinstance` ladder (audit L2)

Trivial refactor in `pipeline.py:97-114`. Existing test still passes.

**Commit:** `refactor(pipeline): isinstance-based stage classification`.

### 5.5 `OllamaClient` cache key collisions (audit L5)

Make `get_chroma_client(path: str | None = None) -> PersistentClient` take the path as a parameter so `lru_cache` keys on it. Drop the `cache_clear()` calls from test `setUp`s.

**Commit:** `refactor(indexer): path-parameterized chromadb client cache`.

### 5.6 De-duplicate log lines between views and services (audit L6)

Pick one: view logs only the "receipt" and "complete" line, services log the rest. Do this in `documents/views.py` first, then `queries/views.py`.

**Commit:** `refactor(views): collapse duplicate logging, single receipt line per request`.

### 5.7 Resolve the `MEDIA_ROOT` local-FS assumption (audit L10)

Add a comment at `settings.py:96` and at `pipeline.py:32` / `views.py:88` stating "Assumes `FileSystemStorage`; if `django-storages` is added, replace `default_storage.path()` with `default_storage.url()` or pass a stream."

**Commit:** `docs(infra): annotate local-FS storage assumption`.

### 5.8 Extract `_DynamicRateMixin` and the four throttles (audit L17)

**New file:** `policyiq/policyiq/throttles.py` with the mixin and the four subclasses. `documents/throttles.py` and `queries/throttles.py` re-export the ones they need. Tests stay in place.

**Commit:** `refactor(throttles): consolidate to project-level module`.

### 5.9 Decide on `_save_upload_and_ingest` and `_validate_pdf` (audit M3)

If Phase 3.3 extracted `ingest_uploaded_pdf`, the view is already a 5-line adapter. Drop the in-`_save_upload_and_ingest` `_validate_pdf` call (the view already validates) and add the size check to `_validate_pdf` using `PDF_MAX_BYTES`.

**Commit:** `refactor(documents): centralize PDF validation, add size check`.

### 5.10 Drop the `Chunk.objects.filter(...).delete()` in reindex (audit M4)

**Per Locked Decision #2, both layers are kept — leave a one-line comment explaining the pre-delete is intentional.** The pre-delete is not strictly redundant; it provides a clean slate before the new index run.

**Commit:** `refactor(documents): annotate reindex pre-delete as intentional`.

### 5.11 Misc. low-priority items

- **L12** (`CHANGELOG.md` lru_cache doc): when 5.5 lands, update the changelog to match the new path-parameterized form.
- **L15** (`extract_pages` memory): file a `// TODO: stream `get_text()` for very large PDFs.` comment in `extractor.py:26-30`. No commit needed.
- **L16** (`clean_pages` two-pass): same — `// TODO: fuse with single-pass counter.` No commit.
- **L19** (`extract_pages` exception type, audit M13): wrap `FileNotFoundError` and `ValueError` in `ExtractionError` at the extractor boundary. Update the test that codified the wrong type. **Commit:** `fix(extractor): raise domain ExtractionError consistently`.
- **L20** (`/api/tags` health endpoint): done implicitly by Phase 0.2's `ollama_client.ping()`.
- **L21** (`clean_pages`, `extract_pages` deferred): already filed under L15/L16.
