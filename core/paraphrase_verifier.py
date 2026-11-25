from schemas.evaluation import ParaphraseEvaluation
from core.prompts import PARAPHRASE_SYSTEM, PARAPHRASE_TEMPLATE
from core.ollama_client import generate

def verify_paraphrase(claim: str, passage: str) -> ParaphraseEvaluation:
    prompt = PARAPHRASE_TEMPLATE.format(student_claim=claim, source_passage=passage)
    return generate(PARAPHRASE_SYSTEM, prompt, ParaphraseEvaluation)
