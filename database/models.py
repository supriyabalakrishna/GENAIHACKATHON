from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.orm import relationship
from .connection import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    indexing_status = Column(String, default="Uploaded")
    page_count = Column(Integer)
    chunk_count = Column(Integer, default=0)
    error_message = Column(Text)

class Assignment(Base):
    __tablename__ = "assignments"
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    description = Column(Text, default="")
    due_date = Column(DateTime)
    status = Column(String, default="draft")
    allow_revisions = Column(Boolean, default=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    documents = relationship("Document", secondary="assignment_documents")
    questions = relationship("Question", back_populates="assignment", cascade="all, delete-orphan")

class AssignmentDocument(Base):
    __tablename__ = "assignment_documents"
    assignment_id = Column(Integer, ForeignKey("assignments.id"), primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id"), primary_key=True)

class Question(Base):
    __tablename__ = "questions"
    id = Column(Integer, primary_key=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=False)
    question_text = Column(Text, nullable=False)
    question_order = Column(Integer, nullable=False)
    max_marks = Column(Float, default=10)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    assignment = relationship("Assignment", back_populates="questions")
    key_points = relationship("QuestionKeyPoint", back_populates="question", cascade="all, delete-orphan")

class QuestionKeyPoint(Base):
    __tablename__ = "question_key_points"
    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    point_text = Column(Text, nullable=False)
    point_order = Column(Integer, nullable=False)
    source_chunk_ids = Column(JSON, default=list)
    is_teacher_edited = Column(Boolean, default=False)
    question = relationship("Question", back_populates="key_points")

class Submission(Base):
    __tablename__ = "submissions"
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    answer_text = Column(Text, nullable=False)
    submitted_at = Column(DateTime, default=datetime.utcnow)
    audit_status = Column(String, default="queued")
    error_message = Column(Text)
    revision_of = Column(Integer, ForeignKey("submissions.id"))

class Claim(Base):
    __tablename__ = "claims"
    id = Column(Integer, primary_key=True)
    submission_id = Column(Integer, ForeignKey("submissions.id"), nullable=False)
    claim_text = Column(Text, nullable=False)
    claim_order = Column(Integer, nullable=False)

class Evaluation(Base):
    __tablename__ = "evaluations"
    id = Column(Integer, primary_key=True)
    claim_id = Column(Integer, ForeignKey("claims.id"), nullable=False)
    classification = Column(String, nullable=False)
    relevance = Column(String, nullable=False, default="UNCLEAR", server_default="UNCLEAR")
    explanation = Column(Text, nullable=False)
    review_required = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Citation(Base):
    __tablename__ = "citations"
    id = Column(Integer, primary_key=True)
    evaluation_id = Column(Integer, ForeignKey("evaluations.id"), nullable=False)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    chunk_id = Column(String, nullable=False)
    page_number = Column(Integer)

class TeacherReview(Base):
    __tablename__ = "teacher_reviews"
    id = Column(Integer, primary_key=True)
    evaluation_id = Column(Integer, ForeignKey("evaluations.id"), nullable=False)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    corrected_classification = Column(String, nullable=False)
    review_notes = Column(Text)
    reviewed_at = Column(DateTime, default=datetime.utcnow)

class Grade(Base):
    __tablename__ = "grades"
    id = Column(Integer, primary_key=True)
    submission_id = Column(Integer, ForeignKey("submissions.id"), unique=True, nullable=False)
    ai_marks = Column(Float, nullable=False)
    max_marks = Column(Float, nullable=False)
    key_point_coverage = Column(JSON, default=list)
    ai_feedback = Column(Text, nullable=False)
    teacher_marks = Column(Float)
    teacher_feedback = Column(Text)
    released_to_student = Column(Boolean, default=False)
    graded_at = Column(DateTime, default=datetime.utcnow)
    overridden_by = Column(Integer, ForeignKey("users.id"))
    overridden_at = Column(DateTime)
