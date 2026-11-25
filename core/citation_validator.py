from core.vector_store import get_collection

def validate_citations(evidence_ids: list[str], evidence_passages: list[dict],
                       assigned_document_ids: list[int]) -> tuple[list[str], bool]:
    supplied = {p["chunk_id"] for p in evidence_passages}
    collection = get_collection()
    valid = []
    review = False
    for chunk_id in evidence_ids:
        if chunk_id not in supplied:
            review = True
            continue
        records = collection.get(ids=[chunk_id], include=["metadatas"])
        metas = records.get("metadatas", [])
        if not metas:
            review = True
            continue
        document_id = int(metas[0].get("document_id", -1))
        if document_id not in assigned_document_ids:
            review = True
            continue
        valid.append(chunk_id)
    return valid, review
