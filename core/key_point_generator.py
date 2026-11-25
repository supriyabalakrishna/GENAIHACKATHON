from schemas.evaluation import KeyPointOutput
from core.prompts import KEY_POINT_SYSTEM, KEY_POINT_TEMPLATE
from core.ollama_client import generate, OllamaError

def generate_key_points(question_text: str, passages: list[dict]) -> KeyPointOutput:
    rendered = "\n\n".join(f"[{p['chunk_id']}] {p['text']}" for p in passages)
    prompt = KEY_POINT_TEMPLATE.format(question_text=question_text, retrieved_passages=rendered or "No passages retrieved.")
    allowed_ids = {p["chunk_id"] for p in passages}
    result = generate(KEY_POINT_SYSTEM, prompt, KeyPointOutput)
    invalid_ids = {citation for point in result.key_points for citation in point.evidence_ids if citation not in allowed_ids}
    if invalid_ids:
        retry_prompt = (
            f"{prompt}\n\nValid passage IDs: {sorted(allowed_ids)}\n"
            f"Your previous response cited invalid IDs: {sorted(invalid_ids)}. "
            "Regenerate the complete key_points object and use only IDs from the valid passage ID list."
        )
        result = generate(KEY_POINT_SYSTEM, retry_prompt, KeyPointOutput)
        invalid_ids = {citation for point in result.key_points for citation in point.evidence_ids if citation not in allowed_ids}
        if invalid_ids:
            raise OllamaError(f"Key-point response cited passages that were not supplied: {', '.join(sorted(invalid_ids))}")
    if any(not point.evidence_ids for point in result.key_points):
        raise OllamaError("Key-point response included a point without a source citation.")
    return result
