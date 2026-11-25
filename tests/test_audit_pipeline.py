from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core import audit_pipeline
from core.audit_pipeline import reset_failed_submission
from database.connection import Base
from database.models import Assignment, Claim, Document, Evaluation, Grade, Question, QuestionKeyPoint, Submission, User
from schemas.claim import ClaimExtraction, ClaimItem
from schemas.evaluation import ClaimEvaluation, CoverageFeedback, ParaphraseEvaluation


def test_submission_is_graded_without_teacher_key_points(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False)
    db = session_factory()

    teacher = User(id=1, name="Teacher", email="teacher@pipeline.test", password_hash="x", role="teacher")
    student = User(id=2, name="Student", email="student@pipeline.test", password_hash="x", role="student")
    document = Document(
        id=1, filename="reading.pdf", file_path="reading.pdf", file_type="pdf",
        uploaded_by=1, indexing_status="Indexed", chunk_count=1,
    )
    assignment = Assignment(id=1, title="Published", status="published", created_by=1)
    assignment.documents.append(document)
    question = Question(
        id=1, assignment_id=1, question_text="Explain the source.", question_order=1,
        max_marks=10, created_by=1,
    )
    submission = Submission(
        id=1, student_id=2, question_id=1, answer_text="A supported claim. An unknown claim.",
        audit_status="queued",
    )
    db.add_all([teacher, student, assignment, question, submission])
    db.commit()

    passage = {
        "chunk_id": "doc1_p1_c1",
        "text": "The reading supports the first claim.",
        "metadata": {"document_id": 1, "page_number": 1},
    }
    monkeypatch.setattr(audit_pipeline, "ensure_models", lambda: None)
    monkeypatch.setattr(
        audit_pipeline,
        "extract_claims",
        lambda answer: ClaimExtraction(claims=[
            ClaimItem(claim_id=1, claim="A supported claim."),
            ClaimItem(claim_id=2, claim="An unknown claim."),
        ]),
    )
    retrieved = iter([[passage], []])
    monkeypatch.setattr(audit_pipeline, "retrieve", lambda *args: next(retrieved))
    monkeypatch.setattr(
        audit_pipeline,
        "verify_claim",
        lambda *args: ClaimEvaluation(
            classification="SUPPORTED",
            relevance="ON_TOPIC",
            evidence_ids=["doc1_p1_c1"],
            explanation="The cited page supports this claim.",
        ),
    )
    monkeypatch.setattr(
        audit_pipeline,
        "validate_citations",
        lambda evidence_ids, passages, assigned_ids: (["doc1_p1_c1"] if passages else [], False),
    )
    monkeypatch.setattr(
        audit_pipeline,
        "verify_paraphrase",
        lambda *args: ParaphraseEvaluation(
            paraphrase_status="VALID_PARAPHRASE", meaning_preserved=True, explanation="Meaning is preserved."
        ),
    )
    monkeypatch.setattr(
        audit_pipeline,
        "generate",
        lambda *args: CoverageFeedback(coverage=[], feedback="One claim is supported; one needs evidence."),
    )

    audit_pipeline.audit_submission(db, db.get(Submission, 1))

    saved_submission = db.get(Submission, 1)
    grade = db.query(Grade).filter_by(submission_id=1).one()
    evaluations = db.query(Evaluation).order_by(Evaluation.id).all()
    assert saved_submission.audit_status == "completed_with_flags"
    assert grade.ai_marks == 5.0
    assert grade.key_point_coverage == []
    assert len(evaluations) == 2
    assert evaluations[0].relevance == "ON_TOPIC"
    assert evaluations[1].relevance == "UNCLEAR"
    db.close()
    engine.dispose()


def test_supported_claims_get_provisional_credit_when_keypoint_coverage_is_zero(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False)
    db = session_factory()

    teacher = User(id=1, name="Teacher", email="fallback-teacher@test", password_hash="x", role="teacher")
    student = User(id=2, name="Student", email="fallback-student@test", password_hash="x", role="student")
    document = Document(
        id=1, filename="reading.pdf", file_path="reading.pdf", file_type="pdf",
        uploaded_by=1, indexing_status="Indexed", chunk_count=1,
    )
    assignment = Assignment(id=1, title="Published", status="published", created_by=1)
    assignment.documents.append(document)
    question = Question(
        id=1, assignment_id=1, question_text="Explain the source.", question_order=1,
        max_marks=10, created_by=1,
    )
    question.key_points.extend([
        QuestionKeyPoint(point_text="First key point", point_order=1),
        QuestionKeyPoint(point_text="Second key point", point_order=2),
    ])
    submission = Submission(
        id=1, student_id=2, question_id=1, answer_text="A supported claim.",
        audit_status="queued",
    )
    db.add_all([teacher, student, assignment, question, submission])
    db.commit()

    passage = {
        "chunk_id": "doc1_p1_c1",
        "text": "The reading supports the claim.",
        "metadata": {"document_id": 1, "page_number": 1},
    }
    monkeypatch.setattr(audit_pipeline, "ensure_models", lambda: None)
    monkeypatch.setattr(
        audit_pipeline,
        "extract_claims",
        lambda answer: ClaimExtraction(claims=[
            ClaimItem(claim_id=1, claim="A supported claim."),
        ]),
    )
    monkeypatch.setattr(audit_pipeline, "retrieve", lambda *args: [passage])
    monkeypatch.setattr(
        audit_pipeline,
        "verify_claim",
        lambda *args: ClaimEvaluation(
            classification="SUPPORTED",
            relevance="UNCLEAR",
            evidence_ids=["doc1_p1_c1"],
            explanation="The cited page supports this claim.",
        ),
    )
    monkeypatch.setattr(
        audit_pipeline,
        "validate_citations",
        lambda *args: (["doc1_p1_c1"], False),
    )
    monkeypatch.setattr(
        audit_pipeline,
        "verify_paraphrase",
        lambda *args: ParaphraseEvaluation(
            paraphrase_status="VALID_PARAPHRASE", meaning_preserved=True, explanation="Meaning is preserved."
        ),
    )
    monkeypatch.setattr(
        audit_pipeline,
        "generate",
        lambda *args: CoverageFeedback(
            coverage=[
                {"key_point_id": 1, "status": "NOT_COVERED", "claim_ids": []},
                {"key_point_id": 2, "status": "NOT_COVERED", "claim_ids": []},
            ],
            feedback="No coverage was verified.",
        ),
    )

    audit_pipeline.audit_submission(db, db.get(Submission, 1))

    grade = db.query(Grade).filter_by(submission_id=1).one()
    saved_submission = db.get(Submission, 1)
    assert grade.ai_marks == 5.0
    assert "Provisional credit was calculated" in grade.ai_feedback
    assert saved_submission.audit_status == "completed_with_flags"
    db.close()
    engine.dispose()


def test_failed_submission_retry_clears_partial_audit_rows():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False)
    db = session_factory()
    teacher = User(id=1, name="Teacher", email="retry-teacher@test", password_hash="x", role="teacher")
    student = User(id=2, name="Student", email="retry-student@test", password_hash="x", role="student")
    document = Document(id=1, filename="reading.pdf", file_path="x", file_type="pdf", uploaded_by=1)
    assignment = Assignment(id=1, title="Published", status="published", created_by=1)
    assignment.documents.append(document)
    question = Question(id=1, assignment_id=1, question_text="Question", question_order=1, created_by=1)
    submission = Submission(id=1, student_id=2, question_id=1, answer_text="Answer", audit_status="failed")
    claim = Claim(submission_id=1, claim_text="Partial claim", claim_order=1)
    db.add_all([teacher, student, assignment, question, submission, claim])
    db.flush()
    db.add(Evaluation(claim_id=claim.id, classification="SUPPORTED", explanation="Partial", relevance="ON_TOPIC"))
    db.commit()

    reset_failed_submission(db, submission)

    assert submission.audit_status == "queued"
    assert submission.error_message is None
    assert db.query(Claim).filter_by(submission_id=1).count() == 0
    assert db.query(Evaluation).count() == 0
    db.close()
    engine.dispose()
