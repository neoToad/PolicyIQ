# PolicyIQ — Prompt Implementation Plan

A sequenced set of prompts for building PolicyIQ phase by phase. Each prompt assumes the previous one produced working, tested code. Do not move to the next prompt until the current step is verified.

---

## Before You Start

Run these commands first so Ollama is ready when the code calls it:

```bash
ollama pull nomic-embed-text
ollama pull llama3.2
```

---

## Phase 1 — Document Ingestion Pipeline

### 1.1 — Project Scaffolding COMPLETED

> "Create a new Django project called `policyiq` with two apps: `documents` and `queries`. Set up the project settings to use PostgreSQL as the database. Include a `requirements.txt` with Django, djangorestframework, psycopg2-binary, PyMuPDF, chromadb, tiktoken, and requests. Create the base project structure matching this layout:
>
> ```
> policyiq/
> ├── documents/
> │   ├── models.py
> │   ├── services/
> │   │   ├── __init__.py
> │   │   ├── extractor.py
> │   │   ├── chunker.py
> │   │   ├── embedder.py
> │   │   └── indexer.py
> │   └── views.py
> ├── queries/
> │   ├── services/
> │   │   ├── __init__.py
> │   │   ├── retriever.py
> │   │   └── generator.py
> │   └── views.py
> └── templates/
> ```
>
> Don't write any service logic yet — just the scaffold with empty files and the correct imports stubbed in."

---

### 1.2 — Django Models COMPLETED

> "Create the `Document` and `Chunk` Django models in `documents/models.py` for PolicyIQ.
>
> `Document` should store:
> - `id` (UUID primary key)
> - `name` (filename as uploaded)
> - `file_path` (path to stored PDF)
> - `page_count` (integer)
> - `chunk_count` (integer)
> - `uploaded_at` (datetime, auto)
>
> `Chunk` should store:
> - `id` (UUID primary key)
> - `document` (ForeignKey to Document, cascade delete)
> - `page_number` (integer)
> - `token_offset` (integer — position of this chunk in the document token sequence)
> - `text` (TextField)
>
> Include `__str__` methods on both models and generate the migration."

---

### 1.3 — PDF Raw Extraction COMPLETED

> "Build the raw extraction portion of `documents/services/extractor.py` for PolicyIQ.
>
> Write a function `extract_pages(pdf_path: str) -> list[dict]` that:
> - Opens the PDF using PyMuPDF (fitz)
> - Iterates through every page
> - Extracts the raw text from each page using `page.get_text()`
> - Returns a list of dicts, each with `page_number` (1-indexed) and `raw_text`
>
> Do not do any text cleanup yet — just raw extraction and structuring. Include error handling for file not found and corrupted PDFs."

---

### 1.4 — PDF Text Cleanup COMPLETED

> "Build the cleanup portion of `documents/services/extractor.py` for PolicyIQ. I already have `extract_pages()` working — now add a `clean_pages(pages: list[dict]) -> list[dict]` function that takes the raw output and:
> - Strips repeated header and footer lines (lines that appear on 3 or more pages verbatim)
> - Removes page number artifacts (lines that are just a number or 'Page X of Y')
> - Rejoins lines that were split mid-sentence due to PDF column layout (a line ending without punctuation followed by a lowercase continuation)
> - Strips leading/trailing whitespace from each page's text
>
> Return the same list structure with a `cleaned_text` field added to each dict alongside the original `raw_text`."

---

### 1.5 — Chunker COMPLETED
> "Build `documents/services/chunker.py` for PolicyIQ.
>
> Write a function `chunk_pages(pages: list[dict], chunk_size: int = 500, overlap: int = 50) -> list[dict]` that:
> - Takes the cleaned page output from the extractor
> - Uses `tiktoken` with the `cl100k_base` encoding to count tokens
> - Splits the text into chunks of `chunk_size` tokens with `overlap` token overlap between consecutive chunks
> - Tracks which page number each chunk originated from (if a chunk spans pages, use the page where it started)
> - Tracks the token offset of each chunk within the full document token sequence
> - Returns a list of dicts with `text`, `page_number`, and `token_offset`
>
> Include a brief docstring explaining the overlap strategy."

---

### 1.6 — Embedder COMPLETED

> "Build `documents/services/embedder.py` for PolicyIQ.
>
> Write a function `embed_chunks(chunks: list[dict]) -> list[dict]` that:
> - Takes the chunk list output from the chunker
> - For each chunk, calls the Ollama API at `http://localhost:11434/api/embeddings` with model `nomic-embed-text`
> - Adds an `embedding` field (list of floats) to each chunk dict
> - Returns the full chunk list with embeddings attached
>
> Also write a standalone `embed_query(query: str) -> list[float]` function for embedding questions at query time.
>
> Include retry logic (3 attempts, 1 second delay) and raise a clear exception if Ollama is unreachable."

---

### 1.7 — ChromaDB Indexer COMPLETED

> "Build `documents/services/indexer.py` for PolicyIQ.
>
> Write the following functions:
>
> `get_collection(collection_name: str = 'policyiq')` — initializes a ChromaDB persistent client using a path from Django settings (`CHROMA_PERSIST_DIR`), and returns the named collection, creating it if it doesn't exist.
>
> `index_document(document_id: str, chunks: list[dict]) -> int` — takes the embedded chunk list and adds all chunks to ChromaDB with metadata fields `document_id`, `page_number`, and `token_offset`. Returns the count of chunks indexed.
>
> `delete_document(document_id: str)` — removes all chunks for a given document ID from ChromaDB.
>
> Use the chunk's `token_offset` combined with `document_id` as the ChromaDB record ID to ensure uniqueness."

---

### 1.8 — Ingestion View COMPLETED

> "Build the Django upload view in `documents/views.py` for PolicyIQ. This view wires together the full ingestion pipeline.
>
> It should:
> - Accept a POST request with a PDF file upload
> - Save the file to a `MEDIA_ROOT/documents/` directory
> - Run the pipeline in order: `extract_pages` → `clean_pages` → `chunk_pages` → `embed_chunks` → `index_document`
> - Save a `Document` record to PostgreSQL with the correct `page_count` and `chunk_count`
> - Return a JSON response with the document ID, name, page count, and chunk count on success
> - Return a structured error response with a clear message on any pipeline failure
>
> Use Django REST Framework's `APIView`. Do not handle the HTMX frontend yet — just the API endpoint."

---

### 1.9 — Ingestion Smoke Test COMPLETED

> "Write a standalone Python script `test_ingestion.py` (not a Django test — just a script I can run directly) that:
> - Points at a local PDF file path I can configure at the top
> - Calls `extract_pages`, `clean_pages`, `chunk_pages`, and `embed_chunks` in sequence
> - Prints a summary after each step: page count, chunk count, average chunk length, first chunk text preview
> - Checks that embeddings are non-null and the expected dimension (768 for nomic-embed-text)
> - Does NOT hit ChromaDB or PostgreSQL — just validates the pipeline up to and including embeddings
>
> This is for manual testing against an ArXiv PDF before wiring up the full Django view."

---

## Phase 2 — Query Interface

### 2.1 — Retriever

> "Build `queries/services/retriever.py` for PolicyIQ.
>
> Write a function `retrieve_chunks(query: str, document_id: str = None, top_k: int = 5) -> list[dict]` that:
> - Embeds the query using `embed_query()` from the embedder service
> - Queries ChromaDB for the top `top_k` most similar chunks
> - If `document_id` is provided, filters results to that document only
> - Returns a list of dicts with `text`, `page_number`, `document_id`, and `similarity_score` (1 minus the distance)
> - Orders results by similarity score descending
>
> Import the `get_collection` function from the indexer service."

---

### 2.2 — Prompt Builder

> "Build a `build_prompt(question: str, chunks: list[dict], similarity_threshold: float = 0.5) -> str | None` function in `queries/services/generator.py` for PolicyIQ.
>
> The function should:
> - Check if the highest similarity score in the chunks list clears the `similarity_threshold`
> - Return `None` if no chunk clears the threshold (triggering a 'no answer found' response)
> - If chunks are usable, build a prompt string that:
>   - Instructs the LLM to answer only from the provided context
>   - Instructs it never to speculate or add information not present in the context
>   - Presents each chunk labeled with its document name and page number
>   - Ends with the user's question
>
> Return the completed prompt string. Do not call the LLM yet — just build the prompt."

---

### 2.3 — Generator

> "Add a `generate_response(prompt: str)` generator function to `queries/services/generator.py` for PolicyIQ.
>
> The function should:
> - Call the Ollama API at `http://localhost:11434/api/generate` with model `llama3.2`
> - Enable streaming (`stream: true` in the request body)
> - Use `requests` with `stream=True` to read the response line by line
> - Parse each line as JSON and yield the `response` field as it arrives
> - Raise a clear exception if Ollama is unreachable
>
> This is a Python generator function — it should `yield` each token string, not return a full response."

---

### 2.4 — Query View

> "Build the query view in `queries/views.py` for PolicyIQ.
>
> It should:
> - Accept a POST request with `question` (string) and optional `document_id` (UUID string)
> - Run: `retrieve_chunks` → `build_prompt` → `generate_response`
> - If `build_prompt` returns `None`, return a plain JSON response: `{'answer': 'No relevant information found in the uploaded documents.'}`
> - If chunks are found, return a `StreamingHttpResponse` that streams the generator output as plain text
> - Also return the retrieved chunks as a separate JSON field in a response header `X-Citations` (serialized as JSON: list of document name, page number, similarity score, and text preview per chunk)
>
> Use Django REST Framework's `APIView`."

---

### 2.5 — Query Smoke Test

> "Write a standalone Python script `test_query.py` that:
> - Has a configurable question string and optional document ID at the top
> - Calls `retrieve_chunks`, prints each chunk with its similarity score and page number
> - Calls `build_prompt` and prints the full prompt
> - Calls `generate_response` and prints the streamed output token by token to stdout
>
> This is for manually testing the full query pipeline against an already-indexed document before wiring up the HTMX frontend."

---

## Phase 3 — HTMX Frontend

### 3.1 — Base Template

> "Create a Django base template at `templates/base.html` for PolicyIQ.
>
> It should include:
> - HTMX from CDN
> - A clean, minimal CSS layout (no frameworks — just a centered container, readable font, sensible spacing)
> - A top nav with the PolicyIQ name and a link to the upload page and the query page
> - A `{% block content %}` area
>
> Style it for a professional internal tool — not a consumer app. Neutral colors, high contrast, no decoration."

---

### 3.2 — Upload Form

> "Build the HTMX upload form template and corresponding Django view for PolicyIQ.
>
> The template (`templates/documents/upload.html`) should:
> - Extend `base.html`
> - Have a file input that only accepts PDFs
> - POST to the ingestion endpoint using `hx-post` and `hx-encoding='multipart/form-data'`
> - Show a loading indicator while the upload is processing (`hx-indicator`)
> - Swap the response into a result div showing the document name, page count, and chunk count on success, or the error message on failure
>
> The Django view should render this template on GET and return an HTML partial (not JSON) on POST so HTMX can swap it directly."

---

### 3.3 — Upload History

> "Build the upload history view for PolicyIQ.
>
> The template (`templates/documents/history.html`) should:
> - Extend `base.html`
> - Display a table of all ingested documents: name, page count, chunk count, upload date
> - Each row should have a 'Delete' button that sends an HTMX DELETE request and removes the row from the table on success
>
> The Django view should handle GET (render the full history) and DELETE (remove the document from PostgreSQL and ChromaDB via `delete_document`, return an empty 200 response so HTMX removes the row)."

---

### 3.4 — Question Input

> "Build the question input template for PolicyIQ.
>
> The template (`templates/queries/ask.html`) should:
> - Extend `base.html`
> - Have a textarea for the question
> - Have an optional document selector dropdown populated with all uploaded documents (plus an 'All Documents' option)
> - POST to the query view using `hx-post`
> - Stream the response into an answer div using `hx-swap='innerHTML'`
> - Show a loading indicator while the query is running
>
> The answer div should display the streamed text as it arrives."

---

### 3.5 — Citations Panel

> "Build the citations panel for PolicyIQ's query page.
>
> After the answer streams in, the UI should display the source chunks used to generate the answer. Read the `X-Citations` response header (set by the query view) and render a citations panel below the answer showing:
> - Document name
> - Page number
> - Similarity score (as a percentage, rounded to nearest whole number)
> - A short text preview of the passage (first 150 characters)
>
> Use a small JavaScript block in the template to read the header from the HTMX response event and populate the citations panel. Style it as a secondary card below the main answer."

---

## Phase 4 — Polish

### 4.1 — Multi-Document Upload

> "Update the upload view and form in PolicyIQ to support uploading multiple PDFs at once. The form should accept multiple files. The view should process each file through the full ingestion pipeline sequentially and return a summary response listing each document's name and chunk count, or an error per file if any individual file fails. The other files should still complete even if one fails."

---

### 4.2 — Similarity Score Indicator

> "Add a visual similarity score indicator to the citations panel in PolicyIQ. For each citation, show a small colored bar next to the score: green for scores above 0.75, yellow for 0.5–0.75, red below 0.5. Add a tooltip on hover explaining what the score means in plain English: 'How closely this passage matched your question.'"

---

### 4.3 — Admin Delete and Re-index

> "Build a simple admin view in PolicyIQ at `/admin/documents/` that:
> - Lists all documents with their metadata
> - Has a 'Delete' button per document that removes it from both PostgreSQL and ChromaDB
> - Has a 'Re-index' button per document that re-runs the chunker → embedder → indexer pipeline on the stored PDF file without re-extracting or re-uploading
> - Protect the route with Django's `@staff_member_required` decorator"

---

### 4.4 — LLM Config Swap

> "Add a `LLM_BACKEND` setting to PolicyIQ's Django settings that accepts `'ollama'` or `'anthropic'`. Update `queries/services/generator.py` to check this setting and route to either the existing Ollama generator or a new Anthropic API generator that uses `claude-sonnet-4-20250514` via the Anthropic Python SDK. Both paths should use the same `build_prompt()` output and yield streamed tokens. Add `ANTHROPIC_API_KEY` to settings, read from environment variable."

---

### 4.5 — README

> "Write a README.md for PolicyIQ. Include:
> - A plain-English problem statement a non-technical hiring manager can understand
> - A brief explanation of RAG and why it's the right approach here
> - A text-based architecture diagram showing the ingestion pipeline and query pipeline
> - Step-by-step local setup instructions using Ollama (free, no API key needed)
> - Instructions for swapping to the Anthropic API for a production demo
> - A known limitations section covering chunking tradeoffs, PDF extraction messiness, and retrieval gaps on negation
> - A production upgrade path section covering: swap to Anthropic/OpenAI embeddings, move ChromaDB to a hosted vector DB, add authentication
>
> Write it for a GitHub audience — clear, direct, no filler."

---

## Checkpoint Checklist

Use this to verify each phase before moving on:

**After Phase 1:**
- [ ] ArXiv PDF uploads successfully
- [ ] Document appears in PostgreSQL with correct page and chunk count
- [ ] Chunks appear in ChromaDB with correct metadata
- [ ] `test_ingestion.py` passes cleanly

**After Phase 2:**
- [ ] Question returns a streamed answer
- [ ] `X-Citations` header contains correct chunk metadata
- [ ] Low-similarity question returns 'No relevant information found'
- [ ] `test_query.py` passes cleanly

**After Phase 3:**
- [ ] Upload form works end to end in the browser
- [ ] Question input streams answer into the page
- [ ] Citations panel renders below the answer
- [ ] Upload history shows all documents, delete works

**After Phase 4:**
- [ ] Multi-file upload works
- [ ] Anthropic backend swap works with `LLM_BACKEND='anthropic'`
- [ ] README is clear to a non-technical reader
