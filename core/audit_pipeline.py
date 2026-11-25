from datetime import datetime
from sqlalchemy.orm import Session
from database.models import Claim, Evaluation, Citation, Grade, TeacherReview, Submission
from core.ollama_client import ensure_models
from core.claim_extractor import extract_claims
from core.retriever import retrieve
from core.claim_verifier import verify_claim
from core.paraphrase_verifier import verify_paraphrase
from core.citation_validator import validate_citations
from core.grader import calculate_marks, calculate_claim_marks, calculate_keypoint_claim_fallback
from core.ollama_client import generate
from core.prompts import COVERAGE_SYSTEM, COVERAGE_TEMPLATE
from schemas.evaluation import CoverageFeedback

def reset_failed_submission(db: Session, submission: Submission) -> None:
    if submission.audit_status != "failed":
        raise ValueError("Only failed submissions can be retried.")
    if db.query(Grade).filter(Grade.submission_id == submission.id).first():
        raise ValueError("A submission with a saved grade cannot be retried.")
    claim_ids = [
        claim.id for claim in db.query(Claim.id).filter(Claim.submission_id == submission.id).all()
    ]
    evaluation_ids = [
        row.id for row in db.query(Evaluation.id).filter(Evaluation.claim_id.in_(claim_ids)).all()
    ] if claim_ids else []
    if evaluation_ids:
        db.query(Citation).filter(Citation.evaluation_id.in_(evaluation_ids)).delete(synchronize_session=False)
        db.query(TeacherReview).filter(TeacherReview.evaluation_id.in_(evaluation_ids)).delete(synchronize_session=False)
        db.query(Evaluation).filter(Evaluation.id.in_(evaluation_ids)).delete(synchronize_session=False)
    if claim_ids:
        db.query(Claim).filter(Claim.id.in_(claim_ids)).delete(synchronize_session=False)
    submission.audit_status = "queued"
    submission.error_message = None
    db.commit()

def audit_submission(db: Session, submission) -> None:
    ensure_models()
    submission.audit_status = "extracting claims"
    db.commit()
    from database.models import Question
    question = db.get(Question, submission.question_id)
    key_points = sorted(question.key_points, key=lambda k: k.point_order)
    extraction = extract_claims(submission.answer_text)
    assigned_ids = [d.id for d in question.assignment.documents]
    if not assigned_ids:
        submission.audit_status = "failed"
        submission.error_message = "No reading documents are assigned to this question."
        db.commit()
        return

    review_required = False
    contradictions = 0
    saved_claims = []
    supported_claim_ids = set()
    for item in extraction.claims:
        claim = Claim(submission_id=submission.id, claim_text=item.claim, claim_order=item.claim_id)
        db.add(claim)
        db.flush()
        saved_claims.append(claim)
        submission.audit_status = f"verifying claim {item.claim_id} of {len(extraction.claims)}"
        db.commit()
        passages = retrieve(item.claim, assigned_ids)
        if not passages:
            from schemas.evaluation import ClaimEvaluation
            result = ClaimEvaluation(
                classification="INSUFFICIENT_EVIDENCE",
                relevance="UNCLEAR",
                evidence_ids=[],
                explanation="No relevant source evidence was retrieved.",
            )
        else:
            result = verify_claim(item.claim, passages, question.question_text)
        valid_ids, citation_review = validate_citations(result.evidence_ids, passages, assigned_ids)
        if result.classification in ("SUPPORTED", "CONTRADICTED") and not valid_ids:
            result.classification = "INSUFFICIENT_EVIDENCE"
            result.explanation = (
                "No valid source citation was saved, so this claim cannot be marked supported or contradicted."
            )
            citation_review = True
        if result.classification == "SUPPORTED" and result.relevance != "OUT_OF_CONTEXT":
            supported_claim_ids.add(item.claim_id)
        claim_review_required = citation_review or result.relevance in ("UNCLEAR", "OUT_OF_CONTEXT")
        review_required = review_required or claim_review_required
        if result.classification == "CONTRADICTED" and result.relevance == "ON_TOPIC":
            contradictions += 1
        if result.classification in ("SUPPORTED", "CONTRADICTED") and passages:
            paraphrase = verify_paraphrase(item.claim, passages[0]["text"])
            if paraphrase.paraphrase_status == "MEANING_CHANGED" or paraphrase.paraphrase_status == "NOT_ENOUGH_INFORMATION":
                claim_review_required = True
                review_required = True
        evaluation = Evaluation(claim_id=claim.id, classification=result.classification,
                                relevance=result.relevance, explanation=result.explanation,
                                review_required=claim_review_required)
        db.add(evaluation)
        db.flush()
        for chunk_id in valid_ids:
            passage = next(p for p in passages if p["chunk_id"] == chunk_id)
            meta = passage["metadata"]
            db.add(Citation(evaluation_id=evaluation.id,
                            document_id=int(meta["document_id"]),
                            chunk_id=chunk_id,
                            page_number=meta.get("page_number")))

    key_points_payload = [{"id": k.id, "text": k.point_text, "evidence_ids": k.source_chunk_ids} for k in key_points]
    claim_payload = []
    for claim in saved_claims:
        ev = db.query(Evaluation).filter(Evaluation.claim_id == claim.id).first()
        claim_payload.append({"claim_id": claim.claim_order, "claim": claim.claim_text,
                              "classification": ev.classification, "relevance": ev.relevance,
                              "explanation": ev.explanation})
    prompt = COVERAGE_TEMPLATE.format(question_text=question.question_text,
                                      key_points=key_points_payload,
                                      claims_with_classifications=claim_payload)
    try:
        coverage_result = generate(COVERAGE_SYSTEM, prompt, CoverageFeedback)
        coverage = [item.model_dump() for item in coverage_result.coverage]
        feedback = coverage_result.feedback
        if not key_points:
            if coverage:
                review_required = True
            coverage = []
        else:
            valid_key_point_ids = {point.id for point in key_points}
            valid_claim_ids = {claim.claim_order for claim in saved_claims}
            coverage_by_key_point = {}
            for item in coverage:
                key_point_id = item["key_point_id"]
                if key_point_id not in valid_key_point_ids or key_point_id in coverage_by_key_point:
                    review_required = True
                    continue
                valid_ids = list(dict.fromkeys(
                    claim_id for claim_id in item["claim_ids"] if claim_id in valid_claim_ids
                ))
                if len(valid_ids) != len(item["claim_ids"]):
                    review_required = True
                item["claim_ids"] = valid_ids
                coverage_by_key_point[key_point_id] = item
            if len(coverage_by_key_point) != len(key_points):
                review_required = True
            coverage = [
                coverage_by_key_point.get(
                    point.id,
                    {"key_point_id": point.id, "status": "NOT_COVERED", "claim_ids": []},
                )
                for point in key_points
            ]
    except Exception as exc:
        coverage = [{"key_point_id": k.id, "status": "NOT_COVERED", "claim_ids": []} for k in key_points]
        feedback = "Coverage feedback could not be generated because the model response was invalid."
        review_required = True
    # A supported claim with unclear relevance can earn provisional coverage, but remains flagged.
    for item in coverage:
        if item["status"] != "NOT_COVERED" and not set(item["claim_ids"]).intersection(supported_claim_ids):
            item["status"] = "NOT_COVERED"
            review_required = True
    claim_evaluations = [
        db.query(Evaluation).filter(Evaluation.claim_id == claim.id).one()
        for claim in saved_claims
    ]
    claim_classifications = [evaluation.classification for evaluation in claim_evaluations]
    claim_relevances = [evaluation.relevance for evaluation in claim_evaluations]
    if key_points:
        ai_marks = calculate_marks(question.max_marks, coverage, contradictions)
        if ai_marks == 0:
            fallback_marks = calculate_keypoint_claim_fallback(
                question.max_marks,
                len(key_points),
                claim_classifications,
                claim_relevances,
            )
            if fallback_marks > 0:
                ai_marks = fallback_marks
                review_required = True
                feedback = (
                    f"{feedback}\n\nProvisional credit was calculated from source-supported claims because "
                    "key-point coverage could not be verified. Teacher review is required before release."
                )
    else:
        ai_marks = calculate_claim_marks(
            question.max_marks,
            claim_classifications,
            claim_relevances,
        )
    grade = Grade(submission_id=submission.id, ai_marks=ai_marks, max_marks=question.max_marks,
                  key_point_coverage=coverage, ai_feedback=feedback)
    db.add(grade)
    submission.audit_status = "completed_with_flags" if review_required else "completed"
    db.commit()
