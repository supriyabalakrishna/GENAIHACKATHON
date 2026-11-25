from config.settings import settings

def round_half(value: float) -> float:
    return round(value * 2) / 2

def calculate_marks(max_marks: float, coverage: list[dict], contradicted_claim_count: int,
                    contradiction_penalty: float | None = None) -> float:
    total = len(coverage)
    if total == 0:
        return 0.0
    covered = sum(1 for item in coverage if item["status"] == "COVERED")
    partial = sum(1 for item in coverage if item["status"] == "PARTIALLY_COVERED")
    penalty = settings.contradiction_penalty if contradiction_penalty is None else contradiction_penalty
    marks = max_marks * ((covered + 0.5 * partial) / total) - (contradicted_claim_count * penalty * max_marks)
    return round_half(max(0.0, min(max_marks, marks)))

def calculate_claim_marks(max_marks: float, classifications: list[str], relevances: list[str] | None = None,
                          contradiction_penalty: float | None = None) -> float:
    if not classifications:
        return 0.0
    if relevances is None:
        relevances = ["ON_TOPIC"] * len(classifications)
    supported = sum(value == "SUPPORTED" and relevance != "OUT_OF_CONTEXT"
                    for value, relevance in zip(classifications, relevances))
    contradicted = sum(value == "CONTRADICTED" and relevance == "ON_TOPIC"
                       for value, relevance in zip(classifications, relevances))
    penalty = settings.contradiction_penalty if contradiction_penalty is None else contradiction_penalty
    marks = max_marks * (supported / len(classifications)) - (contradicted * penalty * max_marks)
    return round_half(max(0.0, min(max_marks, marks)))

def calculate_keypoint_claim_fallback(max_marks: float, key_point_count: int,
                                      classifications: list[str], relevances: list[str] | None = None,
                                      contradiction_penalty: float | None = None) -> float:
    if key_point_count <= 0 or not classifications:
        return 0.0
    if relevances is None:
        relevances = ["ON_TOPIC"] * len(classifications)
    supported = sum(value == "SUPPORTED" and relevance != "OUT_OF_CONTEXT"
                    for value, relevance in zip(classifications, relevances))
    keypoint_cap = round_half(max_marks * min(supported / key_point_count, 1.0))
    claim_marks = calculate_claim_marks(
        max_marks, classifications, relevances, contradiction_penalty
    )
    return min(keypoint_cap, claim_marks)
