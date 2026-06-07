<!--
This file is one slice of the 6-phase refactor described in docs/prompts/refactor_prompt.md.
Commit format: <type>(<scope>): <summary> [PhaseN.X]. Read the prompt's Git Setup, TDD Rules, and Locked Decisions sections before starting.
-->

# Phase 2 — Delete-path safety (audit H2)

**Why third:** Similar atomicity problem on the delete path. Now that the pipeline is atomic, the same pattern is easy to apply here. Also tests for the public `DocumentDeleteView` are a precondition for fixing the permission gap (M7).

### 2.1 Extract `delete_document_with_chunks` service (audit H2)

**New file:** `policyiq/documents/services/deletion.py`.

**TDD steps:**
1. **Failing tests** in `policyiq/documents/tests/test_services.py` (new section `DeletionServiceTests`):
   - `test_delete_document_with_chunks_removes_pg_and_chromadb` — happy path, asserts `Chunk.objects.count() == 0` and `delete_document` was called.
   - `test_delete_rolls_back_pg_on_chromadb_failure` — patches `delete_document` to raise, asserts `Document` row still exists.
   - `test_delete_rolls_back_chromadb_on_pg_failure` — harder to simulate cleanly without `transaction.atomic` mocking; instead, assert that the function is wrapped in `transaction.atomic` and that the PG delete happens *after* the ChromaDB delete (use a mock that tracks call order).
   - `test_delete_creates_vector_orphan_marker_on_chromadb_failure` — assert a logger WARNING line is emitted.
2. **Implement** the service: `transaction.atomic()` block, `delete_document(str(document.id))` first, then `document.delete()`. On exception, log and re-raise.
3. **Wire** the two delete views (`views.py:200-211` and `views.py:225-237`) to call the new service. Views shrink to ~3 lines.

**Commit:** `refactor(documents): extract delete_document_with_chunks service with atomic ordering`.

### 2.2 Decide on `DocumentDeleteView` vs `StaffDocumentDeleteView` (audit H2, M7, L18)

**Per Locked Decision #1 in `../refactor_prompt.md`:** drop `DocumentDeleteView`, require staff for all deletes. All delete traffic goes through the staff-only path. This also collapses the L18 finding ("95% identical views") for free.

**Steps:**
- Delete `DocumentDeleteView`, update `urls.py:27` and `templates/documents/history.html:31` to point at the staff URL, and remove the now-redundant view.
- No new `Document.owner` FK; no permission tests for the dropped view.

**Commit:** `refactor(documents): consolidate delete views behind single auth-gated path`.
