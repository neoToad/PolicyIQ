from documents.services.embedder import embed_query
from documents.services.indexer import get_collection


def retrieve_chunks(query: str, document_id: str | None = None, top_k: int = 5) -> list[dict]:
    query_embedding = embed_query(query)
    collection = get_collection()

    where_filter = {"document_id": document_id} if document_id else None
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=where_filter,
    )

    chunks = []
    ids = results.get("ids", [[]])[0]
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    for i in range(len(ids)):
        # ChromaDB default l2 space returns squared L2 distance.
        # nomic-embed-text produces unit vectors, so:
        #   cosine_similarity = 1 - (squared_l2_distance / 2)
        raw_distance = distances[i]
        similarity = max(0.0, round(1 - raw_distance / 2, 4))
        chunks.append(
            {
                "text": documents[i],
                "page_number": metadatas[i].get("page_number"),
                "document_id": metadatas[i].get("document_id"),
                "document_name": metadatas[i].get("document_name", "Unknown"),
                "similarity_score": similarity,
            }
        )

    chunks.sort(key=lambda c: c["similarity_score"], reverse=True)
    return chunks
