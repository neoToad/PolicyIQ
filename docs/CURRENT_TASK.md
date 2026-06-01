# Current Task

**Step**: Phase 5.4 — Batch embedding requests (committing)
**Status**: Implementation complete, all 89 tests pass, ruff clean
**What I'm working on**: Modified `embed_chunks()` to send chunks to Ollama in batches of 32 (configurable via `batch_size` kwarg) via the new `/api/embed` endpoint, which accepts a list of inputs. For a 50-page PDF (~100 chunks), this collapses 100 sequential HTTP calls into ~4 batched calls. On batch failure, falls back to per-chunk sequential calls so a partial outage of the batch endpoint doesn't block ingestion.

**Blockers/Decisions**:
- Switched from the legacy `/api/embeddings` endpoint to the modern `/api/embed` endpoint, which supports batch input. Verified live against the running Ollama instance.
- Single-text paths (`embed_query`, fallback) use the same `/api/embed` endpoint with `input: text` (single string), keeping the code path uniform — no `/api/embeddings` legacy fallback needed.
- Added `_normalize()` helper to share L2-normalization logic between batch and single paths.

**Next step**: Commit Phase 5.4, push, then proceed to Phase 5.5 (rate limiting).
