from pydantic import BaseModel
from typing import Literal

class ClaimEvaluation(BaseModel):
    classification: Literal["SUPPORTED", "CONTRADICTED", "INSUFFICIENT_EVIDENCE"]
    relevance: Literal["ON_TOPIC", "OUT_OF_CONTEXT", "UNCLEAR"]
    evidence_ids: list[str]
    explanation: str

class ParaphraseEvaluation(BaseModel):
    paraphrase_status: Literal["VALID_PARAPHRASE", "MEANING_CHANGED", "NOT_ENOUGH_INFORMATION"]
    meaning_preserved: bool
    explanation: str

class KeyPoint(BaseModel):
    id: int
    text: str
    evidence_ids: list[str]

class KeyPointOutput(BaseModel):
    key_points: list[KeyPoint]

class CoverageItem(BaseModel):
    key_point_id: int
    status: Literal["COVERED", "PARTIALLY_COVERED", "NOT_COVERED"]
    claim_ids: list[int]

class CoverageFeedback(BaseModel):
    coverage: list[CoverageItem]
    feedback: str
