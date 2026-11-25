from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from core import report_generator, vector_store
from core.report_generator import report_csv
from database.connection import Base
from database.models import Assignment, Claim, Citation, Document, Evaluation, Question, Submission, User

def test_csv_report_includes_pdf_evidence_location():
    report = {
        "student": "Student",
        "assignment": "Assignment",
        "question": "Question",
        "claims": [{
            "claim_text": "The claim",
            "classification": "SUPPORTED",
            "relevance": "ON_TOPIC",
            "explanation": "Supported by the source.",
            "citations": [{
                "document_name": "reading.pdf",
                "location": "Page 2",
                "text": "The source passage.",
            }],
        }],
    }
    csv_report = report_csv(report)
    assert "reading.pdf" in csv_report
    assert "Page 2" in csv_report
    assert "The source passage." in csv_report


def test_claim_report_deduplicates_source_chunk_lookup(monkeypatch):
    class Collection:
        def get(self, ids, include):
            assert ids == ["source_chunk"]
            return {
                "ids": ids,
                "documents": ["Evidence from the reading."],
                "metadatas": [{}],
            }

    monkeypatch.setattr(vector_store, "get_collection", lambda: Collection())
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        teacher = User(name="Teacher", email="teacher@report.test", password_hash="x", role="teacher")
        student = User(name="Student", email="student@report.test", password_hash="x", role="student")
        db.add_all([teacher, student])
        db.flush()
        assignment = Assignment(title="Reading", status="published", created_by=teacher.id)
        document = Document(
            filename="reading.pdf",
            file_path="reading.pdf",
            file_type="pdf",
            uploaded_by=teacher.id,
        )
        db.add_all([assignment, document])
        db.flush()
        question = Question(
            assignment_id=assignment.id,
            question_text="What happened?",
            question_order=1,
            created_by=teacher.id,
        )
        db.add(question)
        db.flush()
        submission = Submission(
            student_id=student.id,
            question_id=question.id,
            answer_text="Two claims.",
        )
        db.add(submission)
        db.flush()
        claims = [
            Claim(submission_id=submission.id, claim_text="First claim.", claim_order=1),
            Claim(submission_id=submission.id, claim_text="Second claim.", claim_order=2),
        ]
        db.add_all(claims)
        db.flush()
        evaluations = [
            Evaluation(claim_id=claim.id, classification="SUPPORTED", relevance="ON_TOPIC", explanation="Supported.")
            for claim in claims
        ]
        db.add_all(evaluations)
        db.flush()
        db.add_all([
            Citation(evaluation_id=evaluation.id, document_id=document.id, chunk_id="source_chunk")
            for evaluation in evaluations
        ])
        db.flush()

        report = report_generator.claim_report_rows(db, submission.id)

        assert len(report) == 2
        assert all(row["citations"][0]["text"] == "Evidence from the reading." for row in report)
    engine.dispose()
