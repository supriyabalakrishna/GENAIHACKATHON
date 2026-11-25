from config.settings import settings
from core.vector_store import get_collection
from core.ollama_client import embed

def retrieve(query: str, document_ids: list[int], top_k: int | None = None) -> list[dict]:
    if not document_ids:
        return []
    collection = get_collection()
    vector = embed(query)
    result = collection.query(
        query_embeddings=[vector],
        n_results=top_k or settings.top_k,
        where={"document_id": {"$in": document_ids}},
        include=["documents", "metadatas", "distances"],
    )
    passages = []
    ids = result.get("ids", [[]])[0]
    docs = result.get("documents", [[]])[0]
    metas = result.get("metadatas", [[]])[0]
    dists = result.get("distances", [[]])[0]
    for chunk_id, text, meta, distance in zip(ids, docs, metas, dists):
        passages.append({"chunk_id": chunk_id, "text": text, "metadata": meta, "distance": distance})
    return passages
