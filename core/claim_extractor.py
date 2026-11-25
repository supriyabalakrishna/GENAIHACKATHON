from schemas.claim import ClaimExtraction
from core.prompts import CLAIM_EXTRACTION_SYSTEM, CLAIM_EXTRACTION_TEMPLATE
from core.ollama_client import generate

def extract_claims(answer: str) -> ClaimExtraction:
    prompt = CLAIM_EXTRACTION_TEMPLATE.format(student_answer=answer)
    return generate(CLAIM_EXTRACTION_SYSTEM, prompt, ClaimExtraction)
