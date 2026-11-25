import pytest

from core import ollama_client
from schemas.claim import ClaimExtraction
from pydantic import ValidationError
from schemas.evaluation import ClaimEvaluation

class MockResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {"models": [{"name": "qwen2.5:3b"}, {"name": "nomic-embed-text:latest"}]}


def test_health_accepts_latest_embedding_tag(monkeypatch):
    monkeypatch.setattr(ollama_client.requests, "get", lambda *args, **kwargs: MockResponse())
    assert ollama_client.health() == (True, "Ollama ready")


def test_invalid_model_json_gets_one_repair_retry(monkeypatch):
    responses = iter([
        {"message": {"content": '{"claim_id": 1, "claim": "A claim."}'}},
        {"message": {"content": '{"claims": [{"claim_id": 1, "claim": "A claim."}]}'}},
    ])
    calls = []

    class ChatResponse(MockResponse):
        def json(self):
            return next(responses)

    def post(*args, **kwargs):
        calls.append(kwargs["json"])
        return ChatResponse()

    monkeypatch.setattr(ollama_client.requests, "post", post)
    result = ollama_client.generate("system", "prompt", ClaimExtraction)
    assert result.claims[0].claim == "A claim."
    assert len(calls) == 2
    assert calls[0]["format"] == ClaimExtraction.model_json_schema()


def test_claim_evaluation_requires_explicit_relevance():
    with pytest.raises(ValidationError):
        ClaimEvaluation(
            classification="SUPPORTED",
            evidence_ids=["doc1_p1_c1"],
            explanation="Supported by the source.",
        )
