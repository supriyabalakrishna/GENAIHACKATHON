from pydantic import BaseModel
from typing import Literal

class CoverageRecord(BaseModel):
    key_point_id: int
    status: Literal["COVERED", "PARTIALLY_COVERED", "NOT_COVERED"]
    claim_ids: list[int]

class GradeRecord(BaseModel):
    ai_marks: float
    max_marks: float
    key_point_coverage: list[CoverageRecord]
    ai_feedback: str
