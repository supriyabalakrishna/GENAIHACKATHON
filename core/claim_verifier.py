from schemas.evaluation import ClaimEvaluation
from core.prompts import CLAIM_VERIFICATION_SYSTEM, CLAIM_VERIFICATION_TEMPLATE
from core.ollama_client import generate

def verify_claim(claim: str, passages: list[dict], question_text: str = "") -> ClaimEvaluation:
    evidence = "\n\n".join(f"[{p['chunk_id']}] {p['text']}" for p in passages)
    prompt = CLAIM_VERIFICATION_TEMPLATE.format(
        question_text=question_text,
        student_claim=claim,
        retrieved_passages=evidence or "No passages retrieved.",
    )
    return generate(CLAIM_VERIFICATION_SYSTEM, prompt, ClaimEvaluation)
