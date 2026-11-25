import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth.hashing import hash_password
from database.connection import Base, get_db
from database.models import Assignment, Document, Grade, Question, Submission, User
from main import app


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()
    db.add_all([
        User(name="Teacher", email="teacher@test.local", password_hash=hash_password("TeacherPass123!"), role="teacher"),
        User(name="Student", email="student@test.local", password_hash=hash_password("StudentPass123!"), role="student"),
    ])
    db.commit()
    db.close()

    def override_get_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, follow_redirects=False) as test_client:
        yield test_client, TestingSession
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def csrf_from(response):
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    assert match
    return match.group(1)

def test_home_redirects_to_login(client):
    test_client, _ = client
    response = test_client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


def test_student_can_create_first_time_account(client):
    test_client, session_factory = client
    csrf = csrf_from(test_client.get("/register"))
    response = test_client.post("/register", data={
        "csrf_token": csrf,
        "name": "New Student",
        "email": "new@student.local",
        "password": "LongEnoughPassword1!",
    })
    assert response.status_code == 303
    with session_factory() as db:
        user = db.query(User).filter_by(email="new@student.local").one()
        assert user.role == "student"
        assert user.password_hash != "LongEnoughPassword1!"


def test_role_access_and_unauthenticated_redirect(client):
    test_client, session_factory = client
    with session_factory() as db:
        teacher = db.query(User).filter_by(role="teacher").one()
        db.add(Document(
            filename="reading.txt",
            file_path="reading.txt",
            file_type="txt",
            uploaded_by=teacher.id,
            indexing_status="Indexed",
            chunk_count=1,
        ))
        db.commit()

    response = test_client.get("/teacher/dashboard", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"

    teacher_csrf = csrf_from(test_client.get("/login?role=teacher"))
    teacher_login = test_client.post("/teacher/login", data={
        "csrf_token": teacher_csrf,
        "email": "teacher@test.local",
        "password": "TeacherPass123!",
    })
    assert teacher_login.status_code == 302
    publish_csrf = csrf_from(test_client.get("/teacher/questions"))
    publish_response = test_client.post("/teacher/assignments", data={
        "csrf_token": publish_csrf,
        "title": "Published test assignment",
        "document_ids": "1",
        "question_0": "What does the reading explain?",
        "marks_0": "10",
        "action": "publish",
    })
    assert publish_response.status_code == 302

    with session_factory() as db:
        teacher = db.query(User).filter_by(role="teacher").one()
        legacy = Assignment(title="Legacy published", status="published", created_by=teacher.id)
        db.add(legacy)
        db.flush()
        db.add(Question(
            assignment_id=legacy.id,
            question_text="A previously published question",
            question_order=1,
            created_by=teacher.id,
        ))
        legacy_id = legacy.id
        db.commit()
    attach_csrf = csrf_from(test_client.get("/teacher/questions"))
    attach_response = test_client.post(
        f"/teacher/assignments/{legacy_id}/documents",
        data={"csrf_token": attach_csrf, "document_ids": "1"},
    )
    assert attach_response.status_code == 302
    with session_factory() as db:
        assert len(db.get(Assignment, legacy_id).documents) == 1
        student = db.query(User).filter_by(role="student").one()
        question = db.query(Question).filter_by(assignment_id=legacy_id).one()
        submission = Submission(
            student_id=student.id,
            question_id=question.id,
            answer_text="A submitted answer for the report.",
            audit_status="failed",
            error_message="Previous audit failed.",
        )
        db.add(submission)
        db.commit()
        submission_id = submission.id

    report_table = test_client.get("/teacher/reports/table")
    assert report_table.status_code == 200
    assert "Student" in report_table.text
    report_detail = test_client.get(f"/teacher/reports/{submission_id}")
    assert report_detail.status_code == 200
    assert "A submitted answer for the report." in report_detail.text
    assert "Previous audit failed." in report_detail.text

    with session_factory() as db:
        submission = db.get(Submission, submission_id)
        submission.audit_status = "completed_with_flags"
        submission.error_message = None
        db.add(Grade(
            submission_id=submission_id,
            ai_marks=6.5,
            max_marks=10,
            ai_feedback="A saved test grade.",
            teacher_marks=7.0,
        ))
        db.commit()
    report_detail = test_client.get(f"/teacher/reports/{submission_id}")
    assert report_detail.status_code == 200
    assert "AI-suggested: 6.5 / 10" in report_detail.text
    assert "Teacher final mark: 7.0 / 10" in report_detail.text
    assert "A saved test grade." in report_detail.text

    test_client.cookies.clear()
    csrf = csrf_from(test_client.get("/login?role=student"))
    response = test_client.post("/student/login", data={
        "csrf_token": csrf,
        "email": "student@test.local",
        "password": "StudentPass123!",
    })
    assert response.status_code == 302
    dashboard = test_client.get("/student/dashboard")
    assert dashboard.status_code == 200
    assert "Published test assignment" in dashboard.text
    assert test_client.get(f"/student/submissions/{submission_id}").status_code == 200
    assignments_fragment = test_client.get("/student/assignments/available")
    assert assignments_fragment.status_code == 200
    assert "Published test assignment" in assignments_fragment.text
    assert test_client.get("/student/results/available").status_code == 200
    forbidden = test_client.get("/teacher/dashboard")
    assert forbidden.status_code == 403

    test_client.cookies.clear()
    teacher_csrf = csrf_from(test_client.get("/login?role=teacher"))
    teacher_login = test_client.post("/teacher/login", data={
        "csrf_token": teacher_csrf,
        "email": "teacher@test.local",
        "password": "TeacherPass123!",
    })
    assert teacher_login.status_code == 302
    status = test_client.get("/teacher/documents/status")
    assert status.status_code == 200
    assert "reading.txt" in status.text
