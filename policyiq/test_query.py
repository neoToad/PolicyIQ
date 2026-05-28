import os
import sys

# Ensure the project root is on the path so imports resolve.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "policyiq.settings")

import django

django.setup()

from queries.services.generator import build_prompt, generate_response
from queries.services.retriever import retrieve_chunks

# --- Configuration ---
QUESTION = "What is the main contribution of this paper?"
DOCUMENT_ID = None  # Set to a UUID string to filter by document, or leave as None for all documents.
TOP_K = 5


def main() -> None:
    print(f"Question: {QUESTION}")
    if DOCUMENT_ID:
        print(f"Document filter: {DOCUMENT_ID}")
    else:
        print("Document filter: All documents")
    print("-" * 60)

    # 1. Retrieve chunks
    print("\n[retrieve_chunks]")
    chunks = retrieve_chunks(QUESTION, document_id=DOCUMENT_ID, top_k=TOP_K)
    if not chunks:
        print("No chunks retrieved.")
        return

    for idx, chunk in enumerate(chunks, start=1):
        doc_name = chunk.get("document_name", "Unknown")
        page = chunk.get("page_number", "?")
        score = chunk.get("similarity_score", 0.0)
        preview = chunk.get("text", "")[:150].replace("\n", " ")
        print(f"  {idx}. [{doc_name} - page {page}] score={score:.4f} | {preview}...")

    # 2. Build prompt
    print("\n[build_prompt]")
    prompt = build_prompt(QUESTION, chunks)
    if prompt is None:
        print("No chunk cleared the similarity threshold — prompt is None.")
        return

    print(prompt)

    # 3. Generate response
    print("\n[generate_response]")
    print("-" * 60)
    for token in generate_response(prompt):
        print(token, end="", flush=True)
    print()  # final newline
    print("-" * 60)
    print("\nStream complete.")


if __name__ == "__main__":
    main()