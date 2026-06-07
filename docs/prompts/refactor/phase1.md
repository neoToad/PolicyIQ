<!--
This file is one slice of the 6-phase refactor described in docs/prompts/refactor_prompt.md.
Commit format: <type>(<scope>): <summary> [PhaseN.X]. Read the prompt's Git Setup, TDD Rules, and Locked Decisions sections before starting.
-->

# Phase 1 — Pipeline rollback safety (audit H1)

**Why second:** This is the highest-stakes correctness issue. It depends on the Ollama client (for clearer error types) and on settings (for the chunk/batch counts that drive rollback). It also unlocks the simpler reindex test in M11.

### 1.1 Make the pipeline atomic and ordered (audit H1)

**File:** `policyiq/documents/services/pipeline.py:36-106` and `policyiq/documents/views.py:244-257` (reindex).

**TDD steps:**
1. **Failing tests** in `policyiq/documents/tests/test_pipeline.py` (new section `AtomicityTests`):
   - `test_pipeline_rolls_back_chunks_on_indexer_failure` — patches `index_document` to raise `IndexingError`, drives a real `ingest_document(document)`, asserts `Chunk.objects.filter(document=document).count() == 0` and `Document.page_count is None`.
   - `test_pipeline_rolls_back_indexer_writes_on_bulk_create_failure` — patches `Chunk.objects.bulk_create` to raise `IntegrityError`, asserts no ChromaDB records exist (use a mock `get_chroma_client` that tracks `.delete` calls).
   - `test_pipeline_uses_atomic_block` — uses `assertNumQueries` with `atomic=True` flag, or a simpler `captureOnCommitCallbacks`-style assertion: write a test that confirms PG state and ChromaDB state are committed together or not at all.
   - `test_reindex_does_not_leave_orphan_chunks_on_failure` — runs `StaffDocumentReindexView` with `ingest_document` patched to raise, asserts `Chunk.objects.filter(document=document).count() == 0` after the call (because the pre-delete already happened AND the new run rolled back).
   - `test_pipeline_orders_bulk_create_after_indexer` — patches `index_document` to raise before any `bulk_create` is attempted; asserts no PG writes happened.
2. **Implement:** Wrap the entire `ingest_document` body in `transaction.atomic()`. Run `index_document` first; on success, run `bulk_create`. On any failure inside the `with` block, the transaction rolls back the PG side and we also explicitly call a `delete_document(document_id)` (or a per-chunk-ID rollback if you went that route) to compensate the vector store. The reindex path inherits the same safety because it just calls `ingest_document`.
3. **Verify** all existing pipeline tests in `test_pipeline.py` still pass.

**Commit:** `fix(pipeline): atomic write order with indexer-first, vector compensation on failure`.

### 1.2 Add a swept "vector orphan" marker (audit H2, partial)

Once H1 is fixed, the orphaned-chunk problem is mostly solved. The "vector orphan" marker from the H2 finding can be deferred to a follow-up sweeper job — log a warning with `document_id` and `chunk_count` whenever `index_document` fails after `bulk_create` succeeds, so an ops job can sweep. No new table needed yet.