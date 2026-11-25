from config.settings import settings

def clean_text(text: str) -> str:
    import re
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()

def chunk_text(text: str, doc_id: int, location_type: str = "none",
               location_number: int | None = None) -> list[dict]:
    words = clean_text(text).split()
    size = settings.chunk_size_words
    overlap = settings.chunk_overlap_words
    if not words:
        return []
    chunks = []
    start = 0
    chunk_no = 1
    while start < len(words):
        passage = " ".join(words[start:start + size])
        if location_type == "page":
            chunk_id = f"doc{doc_id}_p{location_number}_c{chunk_no}"
        elif location_type == "slide":
            chunk_id = f"doc{doc_id}_s{location_number}_c{chunk_no}"
        else:
            chunk_id = f"doc{doc_id}_pNA_c{chunk_no}"
        chunks.append({"chunk_id": chunk_id, "text": passage, "page_number": location_number,
                       "location_type": location_type})
        start += max(1, size - overlap)
        chunk_no += 1
    return chunks
