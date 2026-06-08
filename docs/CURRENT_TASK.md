# Current Task

**Phase 4 COMPLETE — test coverage batch. Phase 5 starting: cleanup, dedup, doc fixes.**

> **Note on changelog layout (2026-06-07):** The historical changelog was moved to `docs/changelogs/CHANGELOG.md`. The new top-level `docs/CHANGELOG.md` is the live file for Phase 2+ entries; it points to the archive in its header.

## Status
- Branch `feature/policyiq-refactor` checked out from `main`
- Phase 0, 1, 2, 3 fully complete
- **Phase 4 fully complete** — test coverage batch (4.1–4.9)
- **Phase 5 starting** — cleanup, dead code, dedup, doc fixes
- 4 user decisions locked in:
  1. **Phase 2.2**: Drop `DocumentDeleteView`, staff-only deletes (matches default) — DONE
  2. **Phase 5.1**: **KEEP both** (PG `Chunk` model + ChromaDB text) — user override; document rationale in `CLAUDE.md`
  3. **Phase 5.2**: Delete `queries/services/timing.py` and `queries/tests/test_timing.py` (matches default)
  4. **Phase 4.9**: **KEEP `test_views_pytest.py`, drop `test_views.py`** — DONE in Phase 4

## Phase 4 — done
- **4.1**: `QueryAPIViewOllamaDownTests` + `AskPageViewOllamaDownTests` + `QueryAPIViewErrorEnvelopeTests` in `test_views_ollama_down.py` — 4 tests pinning the 502 + ERROR log contract when Ollama is unreachable (audit H7).
- **4.2**: Empty-ChromaDB and below-threshold paths covered in `QueryAPIViewTests` — `generate_response` not called, no `X-Citations` header (audit H8).
- **4.3**: `StaffDocumentDeleteViewTests` (4 tests): staff delegates to service, non-staff → 302 login, anonymous → 302, 404 on missing doc, 200 on success (audit M7).
- **4.4**: Reindex 500 + chunk-purge ordering — `StaffDocumentReindexView.post` now catches `ingest_document` failures and returns 500 with an ERROR log line; `test_reindex_purges_old_chunks_even_on_failure` uses a real DB to assert the pre-purge ran (audit M9).
- **4.5**: `HistoryPageViewTests` (3 tests): empty-DB no-rows, reverse-chronological ordering, XSS-safe filename rendering via Django auto-escape (audit M10).
- **4.6**: `MidStreamConnectionDropTests` (2 tests): `generate_response` raises `GenerationError` when `ollama.generate` drops mid-stream; `safe_stream` converts to a `<!-- error: ... -->` sentinel (audit M10 + H6).
- **4.7**: Dropped two stale `# pragma: no cover` comments in `queries/services/health.py` — the corresponding tests already cover the lines (audit M12).
- **4.8**: `UploadPartialFailureTests` (5 tests) — full end-to-end matrix of the multi-file upload response shapes (audit M11).
- **4.9**: 
  - L1: New `IsolatedMediaRootMixin` in `policyiq/documents/tests/_isolation.py` gives each test a unique `tempfile.mkdtemp()` MEDIA_ROOT; 19 `@override_settings(MEDIA_ROOT=tempfile.gettempdir())` decorators removed.
  - L8: New `policyiq/queries/constants.py` is the home for `MAX_QUESTION_LOG_CHARS` and `MAX_CHUNKS_IN_LOG`; `retriever.py` and `views.py` import from there.
  - L13: Per Locked Decision #4, `policyiq/queries/tests/test_views.py` removed; `test_views_pytest.py` is the single home for query-view tests.
- **Verify**: `pytest policyiq/` → 246 passed; `ruff check policyiq/` clean; `ruff format --check policyiq/` clean (78 files); `pre-commit run --all-files` clean (10 hooks); `python manage.py check` 0 issues.
- **Audit impact**: closes H7 (Ollama-down), H8 (empty/below-threshold), M7 (delete auth), M9 (reindex failure), M10 (history + mid-stream), M11 (partial-failure), M12 (pragma cleanup), L1 (media isolation), L8 (constants), L13 (test consolidation). Net test count change: +23 new tests, −16 dropped (test_views.py removal), = 246 total.

## Next — Phase 5
Cleanup, dedup, doc fixes. The big items are:
- **5.1**: Document the `Chunk` storage decision in `CLAUDE.md` (Locked Decision #2 — keep both PG and ChromaDB)
- **5.2**: Delete `queries/services/timing.py` and `queries/tests/test_timing.py` (Locked Decision #3); add `# TODO: shared stage timer` markers at the 5 inline `t0 = time.monotonic()` blocks
- Other Phase 5 items per spec: dead code removal, dedup, doc fixes

