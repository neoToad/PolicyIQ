# PolicyIQ

## What It Is
A web app for medical billing specialists that lets you upload payer policy PDFs and ask plain-language questions about them. The app finds the relevant sections and returns a grounded answer with citations showing exactly where in the document the answer came from.

No more ctrl-F through a 50-page Aetna policy. Ask a question, get an answer, see the source.

---

## The Problem It Solves
Medical billing specialists spend significant time manually searching payer policy documents to answer questions that come up during claims work:
- Does this payer cover this procedure?
- What diagnosis codes are required?
- Is prior authorization needed?
- What are the documentation requirements?

These documents are long, dense, and inconsistently formatted across payers. It's slow, repetitive work that happens dozens of times a day.

---

## How It Works (Plain English)
1. User uploads a PDF
2. App cuts the document into small overlapping text chunks (like index cards)
3. Each chunk is converted into a set of numbers (an embedding) that represents its meaning
4. Those embeddings are stored in a vector database — a map where similar meaning = close proximity
5. User asks a question
6. The question is converted into the same kind of numbers
7. App finds the 3-5 chunks closest in meaning to the question
8. Those chunks are handed to an LLM: "Answer this question using only this context"
9. LLM returns a plain-English answer with citations back to the source document

This approach (called RAG — Retrieval Augmented Generation) means the LLM never reads the whole document. It only sees the most relevant passages, keeping responses fast, accurate, and grounded.

---

## Core Features

### Phase 1 — Document Ingestion Pipeline
- Upload a PDF through the UI
- Extract and clean text using PyMuPDF
- Split into overlapping chunks (500 tokens, 50 token overlap)
- Embed each chunk using nomic-embed-text via Ollama (free, local)
- Store vectors in ChromaDB
- Store document metadata in PostgreSQL (name, page count, chunk count, upload date)
- Upload history view

### Phase 2 — Query Interface
- Plain-language question input
- Embed question, retrieve top 5 similar chunks from ChromaDB
- Build grounded prompt and send to LLM (llama3.2 via Ollama locally)
- Stream response back to UI
- Display answer with citations — document name, page number, exact passage used
- "No answer found" handling when similarity score is too low

### Phase 3 — Preloaded Policy Library
- Curated set of public CMS and major payer policy documents loaded out of the box
- User can query the library without uploading anything
- Filter queries to a single document or search across all

### Phase 4 — Polish
- Multi-document upload support
- Similarity score indicator on retrieved chunks
- Admin view to delete documents and re-index
- Swap Ollama for Anthropic/OpenAI API via single config change for production demo

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
| Deployment | Docker + DigitalOcean or Railway |

---

## Project Structure

```
policyiq/
├── documents/
│   ├── models.py           # Document, Chunk models
│   ├── services/
│   │   ├── extractor.py    # PDF text extraction
│   │   ├── chunker.py      # Text splitting logic
│   │   ├── embedder.py     # Ollama embedding calls
│   │   └── indexer.py      # ChromaDB operations
│   └── views.py
├── queries/
│   ├── services/
│   │   ├── retriever.py    # Vector similarity search
│   │   └── generator.py    # LLM prompt + response
│   └── views.py
├── library/                # Preloaded policy document management
└── templates/              # HTMX UI
```

---

## Test Documents

### Start with (clean formatting, good for pipeline development)
- ArXiv academic papers — well-structured PDFs, free to download

### Core use case documents
- **CMS LCD/NCD policies** — cms.gov, Local and National Coverage Determinations
- **Major payer clinical policy bulletins** — Aetna, UnitedHealthcare, Cigna, Anthem (all publicly available)
- **Medicare Administrative Contractor coverage articles** — Noridian, Palmetto GBA, CGS

### Progression
1. Start with ArXiv PDFs while building the ingestion pipeline
2. Switch to CMS LCD documents once pipeline is stable
3. Add major payer policies for the preloaded library

---

## Known Challenges
- **Chunking strategy** — too small loses context, too large degrades retrieval. Overlapping chunks help, tuning required through testing.
- **PDF extraction messiness** — tables, headers, footers, multi-column layouts cause problems. PyMuPDF handles it better than most but cleanup logic will be needed.
- **Retrieval quality** — nomic-embed-text is strong for a free local model but will occasionally miss relevant passages. Document this as a known limitation with a clear upgrade path.

---

## Build Timeline

| Phase | Estimated Time |
|---|---|
| Phase 1 — Ingestion pipeline | 1 weekend |
| Phase 2 — Query interface | 1 weekend |
| Phase 3 — Preloaded library | 3-4 evenings |
| Phase 4 — Polish + README + deploy | 3-4 evenings |

Total: ~3 weeks part-time

---

## Why This Project (Interview Story)
- Solves a real problem from personal experience in medical billing
- Demonstrates full RAG pipeline: ingestion, chunking, embedding, vector search, LLM generation
- Healthcare domain framing is immediately recognizable to hiring managers at Cohere, DrFirst, SCA Health
- Clean services architecture shows production thinking, not tutorial code
- Ollama-first development keeps costs at zero; single config swap to production LLM API
- Directly relevant to roles in Healthcare IT, Data Engineering, Backend Development, and AI Engineering

---

## README Goals
- Clear problem statement a non-technical hiring manager can understand
- Architecture diagram of the RAG pipeline
- How to run locally with Ollama (free)
- How to swap to Anthropic/OpenAI API for production
- Live demo GIF or screenshots
- Known limitations and production upgrade path