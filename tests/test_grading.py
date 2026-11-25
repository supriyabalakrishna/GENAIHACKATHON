from core.grader import calculate_claim_marks, calculate_keypoint_claim_fallback, calculate_marks

def test_full_coverage():
    coverage=[{"status":"COVERED"},{"status":"COVERED"}]
    assert calculate_marks(10,coverage,0)==10.0

def test_partial_and_contradiction():
    coverage=[{"status":"PARTIALLY_COVERED"},{"status":"NOT_COVERED"}]
    assert calculate_marks(10,coverage,1)==1.5

def test_floor_and_cap():
    assert calculate_marks(10,[{"status":"NOT_COVERED"}],10)==0.0
    assert calculate_marks(10,[{"status":"COVERED"}],0)==10.0

def test_claim_based_grading_without_key_points():
    assert calculate_claim_marks(10, ["SUPPORTED", "INSUFFICIENT_EVIDENCE"]) == 5.0
    assert calculate_claim_marks(10, ["SUPPORTED", "SUPPORTED"], ["ON_TOPIC", "OUT_OF_CONTEXT"]) == 5.0

def test_supported_claim_with_unclear_relevance_gets_provisional_credit():
    assert calculate_claim_marks(
        10,
        ["SUPPORTED", "SUPPORTED"],
        ["UNCLEAR", "OUT_OF_CONTEXT"],
    ) == 5.0

def test_keypoint_fallback_awards_capped_credit_for_supported_claims():
    classifications = ["SUPPORTED"] * 7 + ["CONTRADICTED"] * 2
    relevances = ["UNCLEAR"] * 9
    assert calculate_keypoint_claim_fallback(10, 4, classifications, relevances) == 8.0
    assert calculate_keypoint_claim_fallback(
        10, 6, ["SUPPORTED"] * 3, ["UNCLEAR"] * 3
    ) == 5.0
