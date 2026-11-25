from core.chunker import chunk_text

def test_chunk_ids_and_overlap():
    text=" ".join(["word"]*550)
    chunks=chunk_text(text,7,"page",2)
    assert len(chunks)>=2
    assert chunks[0]["chunk_id"].startswith("doc7_p2_c")
    assert chunks[1]["chunk_id"]=="doc7_p2_c2"
