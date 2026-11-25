from pydantic import BaseModel, Field

class ClaimItem(BaseModel):
    claim_id: int
    claim: str = Field(min_length=1)

class ClaimExtraction(BaseModel):
    claims: list[ClaimItem]
