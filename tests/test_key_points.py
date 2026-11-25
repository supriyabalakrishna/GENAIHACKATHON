import pytest

from core import key_point_generator
from core.ollama_client import OllamaError
from schemas.evaluation import KeyPoint, KeyPointOutput


def test_invalid_keypoint_citation_is_repaired(monkeypatch):
    results = iter([
        KeyPointOutput(key_points=[KeyPoint(id=1, text="Grounded point", evidence_ids=["invented"]) ]),
        KeyPointOutput(key_points=[KeyPoint(id=1, text="Grounded point", evidence_ids=["doc4_p1_c1"]) ]),
    ])
    monkeypatch.setattr(key_point_generator, "generate", lambda *args: next(results))
    result = key_point_generator.generate_key_points(
        "Question?",
        [{"chunk_id": "doc4_p1_c1", "text": "Source passage."}],
    )
    assert result.key_points[0].evidence_ids == ["doc4_p1_c1"]


def test_invalid_keypoint_citation_fails_after_repair(monkeypatch):
    monkeypatch.setattr(
        key_point_generator,
        "generate",
        lambda *args: KeyPointOutput(
            key_points=[KeyPoint(id=1, text="Ungrounded point", evidence_ids=["invented"])]
        ),
    )
    with pytest.raises(OllamaError, match="not supplied"):
        key_point_generator.generate_key_points(
            "Question?",
            [{"chunk_id": "doc4_p1_c1", "text": "Source passage."}],
        )
