# Logging Plan

> **Status:** Analysis & proposal — no code changes yet. Awaiting approval before implementation.
> **Audience for the log lines:** Operators (you, running PolicyIQ locally or in prod) who need to answer three recurring questions: *"Why did this upload fail?"*, *"Why was that answer so slow?"*, *"Did the LLM even see the right chunks?"*
> **Implementation depth:** Logger calls in 4 existing service/view files + a small `queries/services/timing.py` helper. No new dependencies, no schema changes, no Celery, no migration.
> **What changes in the log file:** More lines (one per pipeline stage on the upload path, one per ask stage on the query path), and the ask path goes from logging-nothing-on-success to logging-a-complete-narrative.
> **What does NOT change:** The log file path (`logs/policyiq.log`), the two existing formatters (`verbose` for file, `simple` for console), the rotating-file-handler settings (5 MB × 3 backups), and the test-run override that forces loggers to `ERROR`.

---

## 1. Analysis: What's Happening Now

### 1.1 The upload path — sparse and coarse

The upload pipeline runs synchronously inside the HTTP request. From `policyiq/documents/views.py` → `policyiq/documents/services/pipeline.py` → `extractor` → `chunker` → `embedder` → `indexer`, the **only** function in the entire chain that emits `logger.info` is `ingest_document` itself, and it emits exactly four lines per successful run:

```python
# policyiq/documents/services/pipeline.py
logger.info("Starting ingestion for document %s (%s)", document.id, document.name)        # line 27
logger.info("Extracted %d pages from %s", len(pages), document.name)                        # line 30
logger.info("Created %d chunks for %s", len(chunks), document.name)                         # line 34
logger.info("Ingestion complete for %s (%d pages, %d chunks)", ...)                        # line 54
```

What this leaves out when you're trying to answer *"why did this upload fail?"*:

- The HTTP request itself — was the file even received? What was its size, content-type, and uploaded-by user?
- The view layer — `DocumentUploadAPIView.post` (`views.py:225-268`) and `UploadPageView.post` (`views.py:108-147`) catch exceptions and put `str(exc)` into a result dict, but the exception **type, traceback, and stage** are nowhere in the log.
- The extractor — no logging in `extract_pages` or `clean_pages` (corrupt PDFs, empty PDFs, OCR-needed PDFs all fail silently at this layer).
- The chunker — no logging in `chunk_pages` (a 0-chunk result would be invisible).
- The embedder — only `logger.warning` on retries and `logger.error` on final failure (`embedder.py:42, 76, 80, 110, 114`); no success-path lines.
- The indexer — no logging in `index_document` or `delete_document` (ChromaDB write failures surface as `IndexingError` raised into the pipeline, but the indexer itself is silent).
- **Zero timing data** — the four info lines don't tell you whether it was extraction or embedding that took 30 seconds.

### 1.2 The ask path — silence on success

The query pipeline is equally sparse in the opposite direction: **the success path emits zero log lines**. The full ask flow runs through:

```
queries/views.py (AskPageView, QueryAPIView)
  → queries/services/retriever.py:retrieve_chunks
    → documents/services/embedder.py:embed_query   (no log on success)
    → documents/services/indexer.py:get_collection + collection.query (no log)
  → queries/services/citations.py:build_citations   (no log)
  → queries/services/generator.py:build_prompt     (no log)
  → queries/services/generator.py:generate_response
    → _generate_ollama or _generate_anthropic      (warning on retry, error on final failure)
```

So when you ask *"why was that answer so slow?"* or *"did the LLM see the right chunks?"*, the log file has nothing for you. The two existing `WARNING`/`ERROR` lines only fire on failures (`generator.py:42, 46`).

What the success path needs to tell you:

- The question that was asked (truncated to a safe length — policies are sensitive).
- The retrieved chunks — IDs, document names, page numbers, similarity scores.
- The prompt size (chars + estimated tokens) and citation count that went into the model.
- The model backend, time-to-first-token, total tokens generated, and total duration.
- A timing breakdown (embed / retrieve / build-prompt / generate) so you can see *which* stage was slow.

### 1.3 What exists that we can reuse

- **Logger hierarchy is already in place** (`policyiq/settings.py:166-177`): `documents` and `queries` parent loggers with `INFO` level, `propagate=False`, and both console + file handlers. We just need to start emitting through them.
- **Four existing loggers are wired up** at the right grain: `documents.pipeline`, `documents.embedder`, `queries.generator`, `queries.health`. We'll add to that set rather than invent new naming.
- **The `verbose` formatter** (`{levelname} {asctime} {module} {message}`) is already on the file handler and is exactly the right shape for human reading.
- **`time.monotonic()` is already imported** in `queries/services/generator.py:3` and used for retry sleeps — we can use the same primitive for timing deltas.
- **No `print()` in app code** — only the two manual smoke scripts (`test_ingestion.py`, `test_query.py`), which are unaffected.

### 1.4 Constraints / things to respect

- **Per `AGENTS.md`:** TDD — failing tests first, then minimum code to pass. The plan below follows the same red-green-refactor cycle.
- **No new dependencies** — `time.monotonic` is in stdlib, `logging` is already configured.
- **No schema changes** — nothing in this plan needs a migration.
- **PII discipline** — policies are sensitive, prompts can be long, full PDF text is large. Plan: log IDs, sizes, scores, durations, and truncated text; never log full document text or full prompts at INFO. Full prompt text is DEBUG-only and off by default.
- **The test-run override** (`settings.py:195-197`) forces `documents` and `queries` loggers to `ERROR` during tests. Logging tests using `assertLogs` will need to opt in to a lower level (Django's `assertLogs` overrides the logger level for the duration of the `with` block, so this is fine).
- **Streaming responses** — `QueryAPIView` returns a `StreamingHttpResponse`. Timing has to be measured around the iterator; time-to-first-token is the latency signal that matters most for a streaming UX.

---

## 2. The Plan

### 2.1 Goals

1. When an upload fails, the log file tells you **which stage** failed, with **which input**, and **why** (exception type, not just message).
2. When an ask is slow, the log file tells you **which stage** (embed / retrieve / build-prompt / generate) and gives you **time-to-first-token** for streaming.
3. When an answer is bad, the log file tells you **which chunks the LLM actually saw** — IDs, scores, document names, page numbers — and **how big the prompt was**.
4. No new dependencies, no schema changes, no Celery. Just `logger.info` and `logger.debug` at the right places, with timing.
5. The success-path log lines are the default; no per-stage logger toggling required.

### 2.2 The new narrative

#### Upload path (success)

For a 2.3 MB PDF that takes 6.4s end-to-end, the log should now read roughly:

```
INFO  ... pipeline       Starting ingestion for document 8f3a... (policy.pdf)
INFO  ... extractor      Extracted 14 pages from policy.pdf in 1.20s
INFO  ... chunker        Created 87 chunks from policy.pdf (avg 612 chars, min 41, max 1480) in 0.04s
INFO  ... embedder       Embedded 87 chunks in 3 batches in 4.92s
INFO  ... indexer        Indexed 87 vectors in collection 'policyiq_chunks' in 0.21s
INFO  ... pipeline       Ingestion complete for policy.pdf (14 pages, 87 chunks) in 6.40s
```

Plus, from the view layer, the *request* and *validation* lines:

```
INFO  ... documents.views Received upload "policy.pdf" (2.3 MB) from user=alice
INFO  ... documents.views Validated PDF magic bytes for "policy.pdf"
INFO  ... documents.views Wrote "policy.pdf" to media/documents/2026/06/...
INFO  ... documents.views Dispatched ingestion for "policy.pdf" (document_id=8f3a...) in 0.03s
```

#### Upload path (failure)

For a corrupt PDF that explodes inside `extract_pages`, the log should now read:

```
INFO  ... documents.views Received upload "broken.pdf" (1.1 MB) from user=alice
INFO  ... documents.views Validated PDF magic bytes for "broken.pdf"
INFO  ... documents.views Wrote "broken.pdf" to media/documents/...
INFO  ... pipeline       Starting ingestion for document 8f3a... (broken.pdf)
ERROR ... extractor      Failed to extract pages from broken.pdf after 2.10s: <exception type>: <message>
INFO  ... pipeline       Ingestion failed for broken.pdf at stage=extract after 2.10s: <exception type>
ERROR ... documents.views Ingestion failed for "broken.pdf" after 2.13s: <exception type>: <message>
```

The exception **type** is the key addition — two different OOMs currently look identical in the log.

#### Ask path (success)

For a question that takes 3.2s end-to-end, the log should now read roughly:

```
INFO  ... queries.views     Query received: "what's the deductible for an out-of-network ER visit?" (user=bob, top_k=5)
INFO  ... queries.retriever Embedding query (62 chars) in 0.21s
INFO  ... queries.retriever Retrieved 5 chunks from 3 documents (top=0.812, range 0.421-0.812) in 0.04s
INFO  ... queries.retriever Chunks: [policy-a.pdf p.14 (0.812), policy-b.pdf p.3 (0.781), ...]
INFO  ... queries.generator Built prompt: 1842 chars, 4 citations, similarity_threshold=0.5
INFO  ... queries.generator Streaming from ollama (model=llama3.2)
INFO  ... queries.generator First token in 0.48s
INFO  ... queries.generator Generated 187 tokens in 2.95s
INFO  ... queries.views     Streamed answer (187 tokens) for question_id=... in 3.20s
```

#### Ask path (failure)

For an empty-library query:

```
INFO  ... queries.views     Query received: "what's the deductible?" (user=bob, top_k=5)
INFO  ... queries.retriever Embedding query (21 chars) in 0.18s
INFO  ... queries.retriever Retrieved 0 chunks in 0.02s
WARN  ... queries.generator No relevant information found (max similarity 0.000 < threshold 0.500)
INFO  ... queries.views     Returned 'no relevant information' response in 0.22s
```

### 2.3 Files to add / change

| File | Change | Why |
|---|---|---|
| `policyiq/documents/views.py` | **Add** `logger = logging.getLogger("documents.views")` at module top. Add `logger.info` lines at the start of `_save_upload_and_ingest` (received/validated/wrote/dispatched) and at the end (with timing + exception type on failure). Wrap the ingest call in `try/except` so failures land in the log with stage + type. | The view layer is the only place that knows the request context (user, file size, content-type, status). |
| `policyiq/documents/services/pipeline.py` | **Add** timing around each stage. Log the ingest **failure** case (currently silent on exception — it propagates up to the view's exception swallow). Keep the existing 4 info lines, augment them with `in X.YZs` suffixes. | The pipeline knows which stage failed even when the view doesn't. |
| `policyiq/documents/services/extractor.py` | **Add** `logger = logging.getLogger("documents.extractor")`. Log `Extracted N pages from X in T s` on success. Log `ERROR Failed to extract pages from X after T s: <type>: <msg>` on exception. | Currently the only signal of an extraction failure is the `ExtractionError` that bubbles up — no log line. |
| `policyiq/documents/services/chunker.py` | **Add** `logger = logging.getLogger("documents.chunker")`. Log `Created N chunks from X (avg/min/max chars) in T s` on success. | A 0-chunk result is currently invisible. |
| `policyiq/documents/services/indexer.py` | **Add** `logger = logging.getLogger("documents.indexer")`. Log `Indexed N vectors in collection 'X' in T s` on success. Log `ERROR Failed to index N vectors for document_id=X after T s: <type>: <msg>` on exception. | Indexer failures are the most expensive to debug today because ChromaDB errors are often opaque. |
| `policyiq/queries/views.py` | **Add** `logger = logging.getLogger("queries.views")`. Log the query receipt (truncated), the final outcome (streamed answer / no relevant info / error), with timing. | Same rationale as `documents.views` — request context lives here. |
| `policyiq/queries/services/retriever.py` | **Add** `logger = logging.getLogger("queries.retriever")`. Log embed time, retrieve time, chunk count, score range, **and the retrieved chunk IDs+scores+doc names+page numbers** at INFO. | This is the highest-leverage change for "did the LLM see the right chunks?" |
| `policyiq/queries/services/generator.py` | **Augment** the existing `queries.generator` logger. Add: prompt size + citation count before generation; model selection; time-to-first-token; total tokens + duration on completion. Keep the existing `WARNING` retry / `ERROR` final-failure lines. | This is where the LLM call happens; the answer-speed question lives here. |
| `policyiq/queries/services/timing.py` | **New.** Tiny helper: a `stage_timer` context manager that logs `Stage 'X' completed in T.TTs` on exit (success or failure). Used by the view layer so we don't repeat the `t0 = time.monotonic(); ...; logger.info(... in %.2fs, t1-t0)` pattern. | Cuts boilerplate; keeps stage names consistent in the log. |
| `policyiq/documents/tests/test_views.py` | **Add** `DocumentUploadLoggingTests(TestCase)` — assert that a successful upload emits the new view-layer info lines, and that a failed ingest emits the view-layer error line with the exception type. | AGENTS.md: view tests in `test_views.py`. |
| `policyiq/documents/tests/test_pipeline.py` (new) or extend `test_services.py` | **Add** tests asserting pipeline emits the new stage info lines and a failure INFO+ERROR on exception. | Service-level tests. |
| `policyiq/queries/tests/test_views.py` | **Add** `QueryLoggingTests` — assert that a successful streaming query emits the new view-layer info lines (received, streamed, with duration); assert that an empty-library query emits the WARN "no relevant information" line. | AGENTS.md: view tests. |
| `policyiq/queries/tests/test_retriever.py` (new) or extend existing | **Add** tests asserting retriever emits the new info lines, **including the chunk IDs+scores line** (this is the most important new test — it locks the chunk-logging contract in). | Service-level tests. |
| `policyiq/queries/tests/test_generator.py` (new) or extend existing | **Add** tests asserting generator emits prompt-size + model-selection + first-token + completion lines. | Service-level tests. |
| `docs/CHANGELOG.md` | **Append** a new entry following the existing `[PhaseX.Y]` format. | Matches the established changelog convention. |
| `docs/CURRENT_TASK.md` | **Update** to point at this logging work, then back to "None" when done. | Matches the established tracking convention. |

**No changes to:** `models.py`, `migrations/`, `embedder.py` (already logs on failure — no new code needed, though we may add one info line on success to match the pattern), `serializers.py`, `throttles.py`, `exceptions.py`, `forms.py` (doesn't exist), `requirements.txt`, `pyproject.toml`, `.pre-commit-config.yaml`, `policyiq/settings.py` (the `LOGGING` config and the `_is_test_run()` override both stay as-is).

### 2.4 Helper sketch: `timing.py`

```python
# policyiq/queries/services/timing.py
import logging
import time
from contextlib import contextmanager
from typing import Iterator

logger = logging.getLogger("queries.timing")


@contextmanager
def stage_timer(stage: str, logger_: logging.Logger | None = None) -> Iterator[dict]:
    """Log a stage's duration on context exit (success or failure).

    Yields a dict with a single key ``elapsed_s`` that callers can read after
    the block to include the duration in their own log line.

    Usage:
        with stage_timer("ingest") as t:
            do_work()
        logger.info("Ingest did %d things in %.2fs", n, t["elapsed_s"])
    """
    log = logger_ or logger
    t0 = time.monotonic()
    out: dict = {"elapsed_s": 0.0}
    try:
        yield out
    finally:
        out["elapsed_s"] = time.monotonic() - t0
        # NOTE: caller is responsible for emitting the user-facing info line
        # with stage-specific fields. We only capture the duration here.
```

> **Why a helper that doesn't log itself?** To avoid double-logging (one "X done in 1.2s" from the helper and one "X extracted 14 pages" from the service). The helper exists purely to make timing *uniform* and to keep the timing-pair in one place. Service code still owns the human-readable log message; it just reads `t["elapsed_s"]` to include the duration.

### 2.5 Sketch: retriever info lines (the highest-leverage change)

```python
# policyiq/queries/services/retriever.py
import logging
import time

from documents.services.embedder import embed_query
from documents.services.indexer import get_collection

logger = logging.getLogger("queries.retriever")

MAX_QUESTION_LOG_CHARS = 80  # don't dump full questions into INFO logs


def retrieve_chunks(query: str, document_id: str | None = None, top_k: int = 5) -> list[dict]:
    """Retrieve the most semantically similar chunks for a query.

    Embeds the query, queries ChromaDB, and converts squared L2 distances
    into cosine similarity scores. Emits INFO log lines on entry, embed,
    retrieve, and exit so operators can answer "did the LLM see the right
    chunks?" without re-running the request.
    """
    safe_q = (query[:MAX_QUESTION_LOG_CHARS] + "...") if len(query) > MAX_QUESTION_LOG_CHARS else query
    logger.info(
        "Retrieving up to %d chunks for question=%r document_id=%s",
        top_k, safe_q, document_id or "<all>",
    )

    t0 = time.monotonic()
    query_embedding = embed_query(query)
    embed_s = time.monotonic() - t0
    logger.info("Embedded query (%d chars) in %.2fs", len(query), embed_s)

    t0 = time.monotonic()
    collection = get_collection()
    where_filter = {"document_id": document_id} if document_id else None
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=where_filter,
    )
    retrieve_s = time.monotonic() - t0

    # ... existing chunk-construction loop ...

    chunks.sort(key=lambda c: c["similarity_score"], reverse=True)

    if chunks:
        scores = [c["similarity_score"] for c in chunks]
        chunk_summary = ", ".join(
            f"{c['document_name']} p.{c['page_number']} ({c['similarity_score']:.3f})"
            for c in chunks
        )
        logger.info(
            "Retrieved %d chunks from %d documents (top=%.3f, range %.3f-%.3f) in %.2fs",
            len(chunks),
            len({c["document_id"] for c in chunks}),
            max(scores), min(scores), max(scores),
            retrieve_s,
        )
        logger.info("Chunks: [%s]", chunk_summary)
    else:
        logger.info("Retrieved 0 chunks in %.2fs", retrieve_s)

    return chunks
```

> **Why not log full chunk text at INFO?** PII risk — chunks can contain policyholder-identifying text. IDs, scores, doc names, and page numbers are the diagnostic value; the text is not.

### 2.6 Sketch: generator info lines (answer-speed visibility)

```python
# policyiq/queries/services/generator.py (additions, not full rewrite)
logger = logging.getLogger("queries.generator")

# ... existing _generate_ollama and _generate_anthropic unchanged on the failure path ...

def generate_response(prompt: str) -> Iterator[str]:
    """Stream LLM tokens for the given prompt using the configured backend.

    Yields:
        Individual text tokens from the LLM response stream.

    Emits INFO log lines for: backend selection, time-to-first-token,
    total tokens generated, and total generation duration.
    """
    backend = getattr(settings, "LLM_BACKEND", "ollama")
    model_name = OLLAMA_GENERATE_MODEL if backend == "ollama" else ANTHROPIC_MODEL
    logger.info(
        "Streaming from %s (model=%s, prompt=%d chars)",
        backend, model_name, len(prompt),
    )

    t_start = time.monotonic()
    t_first_token: float | None = None
    token_count = 0

    if backend == "ollama":
        gen = _generate_ollama(prompt)
    elif backend == "anthropic":
        gen = _generate_anthropic(prompt)
    else:
        raise ValueError(f"Unsupported LLM_BACKEND: {backend}")

    for token in gen:
        if t_first_token is None:
            t_first_token = time.monotonic() - t_start
            logger.info("First token in %.2fs", t_first_token)
        token_count += 1
        yield token

    logger.info(
        "Generated %d tokens in %.2fs (first-token=%.2fs, backend=%s)",
        token_count,
        time.monotonic() - t_start,
        t_first_token or 0.0,
        backend,
    )
```

### 2.7 Sketch: view-layer logging (upload + query)

```python
# policyiq/documents/views.py (additions, not full rewrite)
logger = logging.getLogger("documents.views")

# In _save_upload_and_ingest, after the file is written and the Document is created:
logger.info(
    "Received upload %r (%.2f MB) from user=%s",
    uploaded_file.name, uploaded_file.size / (1024 * 1024),
    getattr(request.user, "username", "anonymous"),
)
# ... after validation ...
logger.info("Validated PDF magic bytes for %r", uploaded_file.name)
# ... after writing to storage ...
logger.info("Wrote %r to %s", uploaded_file.name, document.file.name)

t0 = time.monotonic()
try:
    ingest_document(document)
    logger.info("Dispatched ingestion for %r (document_id=%s) in %.2fs",
                uploaded_file.name, document.id, time.monotonic() - t0)
except Exception as exc:
    logger.error(
        "Ingestion failed for %r after %.2fs: %s: %s",
        uploaded_file.name, time.monotonic() - t0,
        type(exc).__name__, exc,
    )
    raise
```

```python
# policyiq/queries/views.py (additions, not full rewrite)
logger = logging.getLogger("queries.views")

# In QueryAPIView.post, after validation:
safe_q = (question[:80] + "...") if len(question) > 80 else question
t0 = time.monotonic()
logger.info("Query received: %r (user=%s, top_k=5)", safe_q, request.user.username)

chunks = retrieve_chunks(question, document_id=document_id, top_k=5)
prompt = build_prompt(question, chunks, similarity_threshold=0.5)

if prompt is None:
    logger.info("Returned 'no relevant information' response in %.2fs", time.monotonic() - t0)
    return Response(..., status=200)

citations = build_citations(chunks)
# ... build streaming response as today ...
logger.info("Streaming answer (prompt=%d chars, %d citations) in %.2fs",
            len(prompt), len(citations), time.monotonic() - t0)
return response
```

### 2.8 Test plan

**Unit (no DB where possible; `assertLogs` for the rest):**

- `policyiq/documents/tests/test_views.py::DocumentUploadLoggingTests(TestCase)`:
  - `test_upload_logs_received_line` — patch the ingest to a no-op; assert `"Received upload"` appears in `documents.views` logger output and includes the file size + username.
  - `test_upload_logs_validated_and_written_lines` — assert the two intermediate lines fire.
  - `test_upload_logs_dispatched_line_on_success` — assert `"Dispatched ingestion"` appears with a duration.
  - `test_upload_logs_error_with_exception_type_on_failure` — patch `ingest_document` to raise `ExtractionError`; assert the error line contains the **exception type name** (`ExtractionError`) and a duration.

- `policyiq/documents/tests/test_pipeline.py::PipelineLoggingTests(TestCase)` (new file, mirrors the existing service-test style):
  - `test_pipeline_logs_stage_lines_with_timing` — mock `extract_pages`, `clean_pages`, `chunk_pages`, `embed_chunks`, `index_document`; assert each stage's `documents.{extractor,chunker,embedder,indexer}` logger emits its info line with a duration field.
  - `test_pipeline_logs_failure_at_correct_stage` — mock `chunk_pages` to raise `ChunkingError`; assert the error line identifies the stage and the exception type.
  - `test_pipeline_logs_completion_summary` — assert the final `"Ingestion complete"` line is emitted on success and includes the duration.

- `policyiq/queries/tests/test_views.py::QueryLoggingTests(TestCase)`:
  - `test_query_logs_received_line_with_truncated_question` — assert the question is logged, truncated at 80 chars, and the username is included.
  - `test_query_logs_no_relevant_info_path` — patch `retrieve_chunks` to return `[]`; assert the WARN "no relevant information" line and the view-level "Returned ... response" line both fire.
  - `test_query_logs_streaming_response_with_prompt_size` — happy path; assert the "Streaming answer" line includes prompt char count and citation count.

- `policyiq/queries/tests/test_retriever.py::RetrieverLoggingTests(TestCase)` (new):
  - `test_retriever_logs_chunk_ids_and_scores` — this is the critical test. Mock the ChromaDB collection; assert the `"Chunks: [...]"` line contains the doc names, page numbers, and similarity scores in the expected format. **This test locks the diagnostic contract.**
  - `test_retriever_logs_embed_and_retrieve_durations` — assert both timing lines fire and contain plausible (non-negative) durations.
  - `test_retriever_logs_zero_chunks` — patch the collection to return no results; assert the "Retrieved 0 chunks" line fires (not the chunk-list line).

- `policyiq/queries/tests/test_generator.py::GeneratorLoggingTests(TestCase)`:
  - `test_generator_logs_backend_and_prompt_size` — assert the line `"Streaming from ollama (model=llama3.2, prompt=N chars)"` fires.
  - `test_generator_logs_first_token_timing` — assert the `"First token in T.TTs"` line fires after the first yield.
  - `test_generator_logs_completion_with_token_count` — assert the `"Generated N tokens in T.TTs"` line fires at the end.

- `policyiq/queries/tests/test_timing.py::StageTimerTests(SimpleTestCase)` (new):
  - `test_stage_timer_sets_elapsed_s_on_success` — assert `t["elapsed_s"]` is positive after the block.
  - `test_stage_timer_sets_elapsed_s_on_exception` — assert the duration is still recorded when the block raises (use `try/except` around the `with`).
  - `test_stage_timer_does_not_swallow_exceptions` — assert the exception propagates.

**Manual verification (not a test, but part of done):**
- After all the above, run the dev server, upload a PDF, then ask a question. `tail -f policyiq/logs/policyiq.log` should show the new narrative on both paths.

### 2.9 Implementation order (TDD per AGENTS.md)

1. Add `policyiq/queries/services/timing.py` with **failing tests** in `test_timing.py` first; confirm they fail for the right reason (`ImportError: cannot import name 'stage_timer'`). Then implement.
2. Add retriever logging with **failing tests** in `test_retriever.py` first (the chunk-listing test is the most important — it pins the diagnostic format). Then implement. *(Highest-leverage change goes first because it's the one with the longest "this would have been useful last week" tail.)*
3. Add generator logging with **failing tests** in `test_generator.py` first. Then implement.
4. Add `queries.views` logging with **failing tests** in `test_views.py` first. Then implement.
5. Add `documents.pipeline` timing/failure logging with **failing tests** in `test_pipeline.py` (new) first. Then implement.
6. Add `documents.extractor` / `documents.chunker` / `documents.indexer` logger creation + info/error lines, one file at a time, each with its own test.
7. Add `documents.views` upload-path logging with **failing tests** in `test_views.py` first. Then implement.
8. Run `pre-commit run --all-files` — should be clean.
9. Run full test suite — should be green (102 + ~13 new = ~115).
10. Manual smoke: `tail -f logs/policyiq.log` while uploading + asking; confirm the narrative reads end-to-end.
11. Update `docs/CHANGELOG.md` and `docs/CURRENT_TASK.md`.
12. Commit as `[Phase7.1] Add stage-by-stage upload + ask path logging with timing`.

### 2.10 Out of scope (deliberately)

- **Full prompt text at INFO** — PII risk and disk-bloat risk. DEBUG-only, off by default.
- **JSON / structured logging** — keep the human-readable `verbose` formatter on the file handler. A follow-up phase can add a `json` formatter and a second file handler if/when aggregation becomes a need.
- **A request-correlation middleware** (`request_id`, `user_id` injected into every line) — high value, but a separate phase; mixing it into this work would balloon the test surface.
- **Moving the Django access log lines out of `policyiq.log`** — those are currently arriving because the file handler is attached to the root logger. A future cleanup can move them to a dedicated `access.log`. Out of scope here.
- **Per-test opt-in to silence** — the existing `_is_test_run()` override (force `ERROR` during tests) is what makes the test suite quiet today. We keep that mechanism as-is; the new `assertLogs`-based tests opt in to `INFO` per-test.
- **Logging in `embedder.py` success path** — `embedder.py` already logs retries and final failure; an info line per successful embed call would be 87 lines per upload (one per chunk batch × 1-3 batches). We log at the *batch* level from `pipeline.py` instead and let `embedder` keep its existing failure-only posture.
- **A new logger for the `extractor` / `chunker` / `indexer` modules** — they don't have loggers today. We add them, but they stay at the existing `INFO` level and inherit handlers from the `documents` parent logger. No new entries in `LOGGING["loggers"]`.
- **Changing the test-run override** — the existing `_is_test_run()` mechanism that forces `documents` and `queries` to `ERROR` during tests stays. `assertLogs` overrides the level for the duration of the `with` block, which is the standard pattern.

### 2.11 Risks and open questions

- **Risk: log volume.** Each ask query goes from 0 lines to ~6 lines. Each upload goes from 4 to ~9 lines. At expected traffic this is fine; at very high traffic it would push the 5 MB / 3-backup rotation faster. Mitigation: rotation already exists; can be tuned later.
- **Risk: prompt-size log line at INFO leaks policy text indirectly.** We log *length* (chars), not content. The truncated question at 80 chars is the only textual content, and it was the user's own input. Acceptable.
- **Risk: time-to-first-token for Anthropic.** `_generate_anthropic` yields from `client.messages.stream(...)`. Measuring first-token time requires the iterator to be consumed by the view. The sketch above assumes the view does `for token in gen: yield token` (it does in `QueryAPIView`). For `AskPageView` the iterator is wrapped in a `stream()` generator that yields HTML around the tokens; the timing wrapper still works because the inner loop is unchanged.
- **Risk: streaming response + logging final stats.** The completion-log line ("Generated N tokens in T.TTs") fires *after* the iterator is fully exhausted. With `StreamingHttpResponse`, the iterator is consumed by Django's response handler *after* the view returns. The log line therefore lands in the access log's timeframe, not the view's return-time. That's fine — it's still on the same request thread — but it means the view-level "Streamed answer ... in T s" line uses a different (slightly earlier) duration than the generator's completion line. Both are useful, and the skew is small.
- **Open question: should the retriever's `Chunks: [...]` line cap the number of entries?** At `top_k=5` it lists 5; at higher `top_k` it could be 20+. Cap at the first 10 with a `... and N more` suffix if the list exceeds 10. **Resolved:** yes, cap at 10 with a "+N more" suffix.
- **Open question: should we log the user's `id` or just `username`?** `username` is sufficient for "which user hit this" and is what the existing `django.request` access lines carry. Use `username` (or `"anonymous"` for the upload path's anon case).
- **Resolved:** exception types in error lines use `type(exc).__name__` (e.g. `ExtractionError`, `IndexingError`, `requests.ConnectionError`), not the full repr.
- **Resolved:** DEBUG-only fields are *not* in this plan. Full prompt text and full chunk text stay out of the log entirely; the operators' three questions are answerable from IDs, sizes, scores, and durations.

---

## 3. Alternatives Considered

| Alternative | Why not chosen |
|---|---|
| **JSON / structured logging** | Premature. The three questions operators ask are all answerable from human-readable lines; aggregation isn't a current need. Easy to add later as a second file handler. |
| **A request-correlation middleware now** | High value, but a separate phase. Mixing it in doubles the test surface and the review surface; the three operator questions don't strictly require it (file size + username are enough to disambiguate most cases). |
| **A single `queries.lifecycle` logger** | Tempting (one logger for the whole ask flow) but loses the per-stage granularity. The current naming (`retriever`, `generator`, `views`) is already structured; we extend it rather than replace it. |
| **Log every individual chunk's text at INFO** | PII. We log IDs, doc names, page numbers, and scores — the diagnostic value. |
| **Log full prompt text at INFO** | Same. Length is enough to spot "the prompt is suddenly 50KB" anomalies; content is DEBUG-only at best, and we're not adding it in this phase at all. |
| **Reuse the existing `documents.embedder` / `queries.generator` loggers for the new lines** | Already doing this for `queries.generator`. The new module-level loggers (`documents.extractor`, `documents.chunker`, `documents.indexer`, `queries.retriever`, `queries.views`, `documents.views`) follow the same per-file naming. |
| **A custom `LogRecord` factory that injects `request_id` / `user_id` into every line** | This is the structured-logging path deferred to a later phase. The current `{levelname} {asctime} {module} {message}` formatter stays. |
| **Add a `documents.utils.timing` module instead of `queries.services.timing`** | Cleaner placement; the helper is generic. **Action item for implementation:** put it at `policyiq/common/timing.py` or `policyiq/documents/utils/timing.py` — not under `queries`. (This doc has it under `queries` for narrative simplicity; the implementation will move it.) |
| **Log inside the embedder's `embed_query` call** | `embed_query` is called from both upload (per chunk) and ask (per query). Logging per-call from inside would be 87 calls per upload. Logging at the `embedder`-module-level from the *batch* caller in `pipeline.py` and the per-query caller in `retriever.py` gives us the same information at the right grain. |
| **Suppress the Django access log lines from `policyiq.log`** | Out of scope for this phase; useful signal, and a separate cleanup. |

---

## 4. Acceptance Criteria

The work is "done" when **all** of the following are true:

1. A successful upload produces a complete narrative in `logs/policyiq.log`: `Received upload → Validated → Wrote → Dispatched → Starting ingestion → Extracted N pages → Created N chunks → Indexed N vectors → Ingestion complete in T s`.
2. A failed upload produces an error line that includes the **exception type name** and a duration, attributed to the correct stage (extractor / chunker / embedder / indexer / view).
3. A successful ask produces a complete narrative in `logs/policyiq.log`: `Query received → Embedded query → Retrieved N chunks → Chunks: [...] → Built prompt → Streaming from X → First token in T s → Generated N tokens in T s → Streamed answer in T s`.
4. The `Chunks: [...]` line includes document name, page number, and similarity score for each retrieved chunk, capped at 10 with a `+N more` suffix for larger `top_k`.
5. The ask path's `Streaming from X (model=Y, prompt=N chars)` line fires before the first token; the `First token in T s` and `Generated N tokens in T s` lines fire from inside the generator.
6. Every new log line goes through one of the existing parent loggers (`documents` or `queries`) or the new child loggers (`documents.views`, `documents.extractor`, `documents.chunker`, `documents.indexer`, `queries.views`, `queries.retriever`) — no orphan loggers, no new entries in `LOGGING["loggers"]`.
7. The question text logged at INFO is truncated to 80 characters; full text is never logged.
8. Chunk text, document text, and full prompt text are never logged at INFO or DEBUG in this phase.
9. All new test cases pass; the full test suite is green (~115 tests, up from 102).
10. `ruff check policyiq/` and `ruff format --check policyiq/` are clean.
11. `pre-commit run --all-files` is clean.
12. `docs/CHANGELOG.md` has a new entry for this work; `docs/CURRENT_TASK.md` is updated to "Next step: None" once the build is complete.
13. No new dependencies, no schema changes, no new apps, no changes to `LOGGING` config in `settings.py`.

---

## 5. Estimated Effort

| Task | Estimate |
|---|---|
| `timing.py` helper + tests | 10 min |
| Retriever logging (highest-leverage) + tests | 25 min |
| Generator logging (first-token timing) + tests | 20 min |
| `queries.views` logging + tests | 15 min |
| `pipeline.py` stage timing + failure logging + tests | 20 min |
| `extractor` / `chunker` / `indexer` logger creation + lines + tests | 25 min |
| `documents.views` upload logging + tests | 15 min |
| `pre-commit run --all-files` + full test run | 5 min |
| Manual smoke (upload + ask + tail log) | 5 min |
| Changelog + current-task updates | 5 min |
| **Total** | **~145 min** |

---

## 6. Next Step

**Awaiting approval on this plan.** Once approved, I'll execute it in the TDD order laid out in §2.9. If you'd like to change scope (e.g., drop the chunk-list line, add JSON output, add the request-correlation middleware now), say the word and I'll revise the plan before touching code.
