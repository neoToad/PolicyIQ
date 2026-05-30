# PolicyIQ

A web app for medical billing specialists that lets you upload payer policy PDFs and ask plain-language questions about them. The app finds the relevant sections and returns a grounded answer with citations showing exactly where in the document the answer came from.

No more ctrl-F through a 50-page Aetna policy. Ask a question, get an answer, see the source.

---

## The Problem

Medical billing specialists spend significant time manually searching payer policy documents to answer questions that come up during claims work:

- Does this payer cover this procedure?
- What diagnosis codes are required?
- Is prior authorization needed?
- What are the documentation requirements?

These documents are long, dense, and inconsistently formatted across payers. It's slow, repetitive work that happens dozens of times a day.

---

## Why RAG?

PolicyIQ uses **Retrieval-Augmented Generation (RAG)** instead of feeding entire PDFs to an LLM. Here's why that's the right fit:

1. **Speed** — The LLM only reads the 3–5 most relevant passages, not a 50-page document.
2. **Accuracy** — Answers are grounded in exact text from the source document, not hallucinated.
3. **Cost** — Local embedding and generation via Ollama keeps the stack free to run. A single config swap upgrades to Anthropic for demos.
4. **Citation** — Every answer comes with source references: document name, page number, and the exact passage used.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        INGESTION PIPELINE                        │
├─────────────────────────────────────────────────────────────────┤
│  PDF Upload  →  Extract Text  →  Clean  →  Chunk  →  Embed  →  Index │
│       │            │             │        │        │        │    │
│       ▼            ▼             ▼        ▼        ▼        ▼    ▼
│   Django View   PyMuPDF      Headers   Tiktoken  Ollama  ChromaDB
│   (POST)        (fitz)       /Footers   500/50    nomic-          │
│                              /Artifacts overlap   embed-text      │
│                                                            PG Meta │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                         QUERY PIPELINE                           │
├─────────────────────────────────────────────────────────────────┤
│  Question  →  Embed  →  Retrieve Top 5  →  Build Prompt  →  LLM │
│      │         │            │               │              │    │
│      ▼         ▼            ▼               ▼              ▼    ▼
│  HTMX Form  Ollama      ChromaDB         Grounded      Ollama │
│  (textarea) nomic-      similarity       prompt           llama3.2│
│             embed-text    search         + citations      Anthropic│
│                                                           (config)│
└─────────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Tool |
|---|---|
| Backend | Django + Django REST Framework |
| Frontend | HTMX |
| Database | PostgreSQL |
| Vector Store | ChromaDB (local) |
| Embeddings | nomic-embed-text via Ollama |
| LLM | llama3.2 via Ollama (dev) / Anthropic API (demo) |
| PDF Extraction | PyMuPDF (fitz) |

---

## Local Setup (Free — Ollama)

### Prerequisites

- Python 3.11+
- PostgreSQL running locally with database `policyiq`
- Ollama installed and running at `http://localhost:11434`

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd policyiq
pip install -r requirements.txt
```

### 2. Pull the Ollama models

```bash
ollama pull nomic-embed-text
ollama pull llama3.2
```

### 3. Configure PostgreSQL

Create a `.env` file in the repo root:

```env
POSTGRES_DB=policyiq
POSTGRES_USER=policyiq
POSTGRES_PASSWORD=policyiq
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
```

Then create the database and user in PostgreSQL.

### 4. Run migrations

```bash
cd policyiq
python manage.py migrate
```

### 5. Start the server

```bash
python manage.py runserver
```

Visit `http://localhost:8000/upload/` to upload a PDF and `http://localhost:8000/ask/` to query it.

---

## Production Demo (Anthropic API)

To swap from local Ollama to Anthropic for a higher-quality demo, change one setting:

```env
LLM_BACKEND=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

The embedding model stays on Ollama (free, local). Only the generation layer swaps to Anthropic's `claude-sonnet-4-20250514`.

No code changes required. Restart the server and queries will route to Anthropic automatically.

---

## Known Limitations

- **Chunking tradeoffs** — Chunks are 500 tokens with 50-token overlap. This works well for most policy language but can split tables or cross-references in awkward places. Tuning chunk size per document type is a known improvement path.
- **PDF extraction messiness** — PyMuPDF handles most layouts well, but multi-column documents, scanned pages, and complex tables can produce garbled text. Cleanup logic strips repeated headers/footers and rejoins mid-sentence breaks, but edge cases remain.
- **Retrieval gaps on negation** — The embedding model (`nomic-embed-text`) is strong for a free local model but can miss passages that answer negatively (e.g., "Prior authorization is *not* required"). Similarity search is fundamentally semantic, not logical.

---

## Production Upgrade Path

1. **Swap embeddings** — Replace `nomic-embed-text` via Ollama with Anthropic or OpenAI embeddings for higher retrieval accuracy. The embedder service is a thin wrapper; the swap is a one-line model name change plus API credentials.
2. **Move to a hosted vector database** — ChromaDB runs locally for development. For production, migrate to Pinecone, Weaviate, or pgvector (PostgreSQL extension) to get persistence, replication, and scaling.
3. **Add authentication and authorization** — The current stack uses Django's built-in auth for the admin view but the public upload/query endpoints are open. Add login-required decorators, user-scoped document collections, and audit logging for production use.

---

## Project Structure

```
policyiq/
├── documents/
│   ├── models.py              # Document, Chunk
│   ├── services/
│   │   ├── extractor.py       # PDF text extraction + cleanup
│   │   ├── chunker.py         # Token-based sliding window chunks
│   │   ├── embedder.py        # Ollama embedding calls
│   │   └── indexer.py         # ChromaDB add/delete
│   └── views.py               # Upload, history, admin, delete, reindex
├── queries/
│   ├── services/
│   │   ├── retriever.py       # Vector similarity search
│   │   └── generator.py       # Prompt builder + LLM dispatch
│   └── views.py               # Query API + HTMX page
├── templates/                 # HTMX frontend
└── manage.py
```

---

## License

MIT
