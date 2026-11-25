import logging

from database.connection import SessionLocal
from database.models import Submission
from core.audit_pipeline import audit_submission

logger = logging.getLogger(__name__)

def run_audit(submission_id: int) -> None:
    db = SessionLocal()
    try:
        submission = db.get(Submission, submission_id)
        if submission is None:
            logger.error("Submission %s disappeared before its audit started", submission_id)
            return
        audit_submission(db, submission)
    except Exception as exc:
        db.rollback()
        submission = db.get(Submission, submission_id)
        if submission is not None:
            submission.audit_status = "failed"
            submission.error_message = str(exc)
            db.commit()
        logger.exception("Audit failed for submission %s", submission_id)
    finally:
        db.close()
