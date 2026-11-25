from schemas.claim import ClaimExtraction
from pydantic import ValidationError

def test_claim_schema():
    data=ClaimExtraction.model_validate({"claims":[{"claim_id":1,"claim":"Supervised learning uses labeled data."}]})
    assert data.claims[0].claim=="Supervised learning uses labeled data."

def test_claim_schema_rejects_empty():
    try:
        ClaimExtraction.model_validate({"claims":[{"claim_id":1,"claim":""}]})
        assert False
    except ValidationError:
        assert True
