import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    Principal,
    get_db,
    require_faculty_project,
    require_project_access,
)
from app.core.config import settings
from app.db.models import (
    AuthAccount,
    Project,
    ProjectMember,
    Student,
    Submission,
    SubmissionReview,
)
from app.services.n8n_notifier import generate_marks_event_id, notify_student_marks

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/projects/{project_id}/submissions/{submission_id}/reviews",
    tags=["Reviews"],
)


class ReviewCreate(BaseModel):
    score: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Numerical score between 0.0 and 100.0",
    )
    feedback: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Written qualitative feedback",
    )


class ReviewUpdate(BaseModel):
    score: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Numerical score between 0.0 and 100.0",
    )
    feedback: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Written qualitative feedback",
    )


class ReviewResponse(BaseModel):
    id: int
    submission_id: int
    project_id: int
    faculty_account_id: int
    reviewer_name: str
    reviewer_email: str
    score: float
    feedback: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


def _serialize_review(review: SubmissionReview, account: AuthAccount | None = None) -> dict:
    faculty = account or review.faculty_account
    reviewer_name = (
        faculty.faculty_name or faculty.email
        if faculty
        else "Faculty Reviewer"
    )
    reviewer_email = faculty.email if faculty else ""
    return {
        "id": review.id,
        "submission_id": review.submission_id,
        "project_id": review.project_id,
        "faculty_account_id": review.faculty_account_id,
        "reviewer_name": reviewer_name,
        "reviewer_email": reviewer_email,
        "score": review.score,
        "feedback": review.feedback,
        "created_at": review.created_at,
        "updated_at": review.updated_at,
    }


def _get_submission_or_404(project_id: int, submission_id: int, db: Session) -> Submission:
    submission = (
        db.query(Submission)
        .filter_by(id=submission_id, project_id=project_id)
        .first()
    )
    if submission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found for this project.",
        )
    return submission


def _dispatch_marks_notification(
    *,
    project_id: int,
    submission: Submission,
    review: SubmissionReview,
    account: Principal,
    db: Session,
) -> None:
    """Safely resolve student details and trigger the marks update notification.

    Runs strictly after a successful database commit. Handled safely with logging;
    any unexpected error will never affect the committed review or fail the API call.
    Direct HTTP delivery is best-effort and not guaranteed.
    """
    try:
        project = db.get(Project, project_id)
        project_name = project.title if project else f"Project {project_id}"
        submission_title = (
            f"Week {submission.week_number} Submission \u2013 {project_name}"
            if submission.week_number is not None
            else f"Submission {submission.id} \u2013 {project_name}"
        )

        faculty_account = db.get(AuthAccount, account.id)
        reviewer_name = (
            faculty_account.faculty_name
            or faculty_account.email
            if faculty_account
            else "Faculty Reviewer"
        )

        # Resolve authoritative student(s) from project membership
        students = (
            db.query(Student)
            .join(ProjectMember, ProjectMember.student_id == Student.id)
            .filter(ProjectMember.project_id == project_id)
            .order_by(
                case((ProjectMember.role == "LEADER", 0), else_=1),
                ProjectMember.id.asc(),
            )
            .all()
        )

        if not students:
            logger.warning(
                "n8n marks notification skipped for submission %s: no students assigned to project %s.",
                submission.id,
                project_id,
            )
            return

        frontend_url = None
        if settings.FRONTEND_URL:
            frontend_url = f"{settings.FRONTEND_URL.rstrip('/')}/#reviews"

        for student in students:
            event_id = generate_marks_event_id(
                review_id=review.id,
                student_id=student.id,
                score=review.score,
                updated_at=review.updated_at,
            )
            notify_student_marks(
                event_id=event_id,
                student_id=student.id,
                student_name=student.name,
                student_email=student.email,
                project_id=project_id,
                project_name=project_name,
                submission_id=submission.id,
                submission_title=submission_title,
                marks_awarded=review.score,
                max_marks=100.0,
                updated_at=review.updated_at,
                updated_by=reviewer_name,
                frontend_url=frontend_url,
                feedback=review.feedback,
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Unexpected error dispatching marks notification for review %s: %s",
            review.id,
            exc,
        )


@router.post(
    "/",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_review(
    project_id: int,
    submission_id: int,
    data: ReviewCreate,
    account: Principal = Depends(require_faculty_project),
    db: Session = Depends(get_db),
):
    submission = _get_submission_or_404(project_id, submission_id, db)

    # Policy: One active review per faculty reviewer per submission.
    existing = (
        db.query(SubmissionReview)
        .filter_by(
            submission_id=submission.id,
            faculty_account_id=account.id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A review has already been submitted for this submission. Update the existing review instead.",
        )

    now = datetime.now(timezone.utc)
    cleaned_feedback = data.feedback.strip()
    if not cleaned_feedback:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Feedback must contain non-whitespace text.",
        )

    review = SubmissionReview(
        submission_id=submission.id,
        project_id=project_id,
        faculty_account_id=account.id,
        score=data.score,
        feedback=cleaned_feedback,
        created_at=now,
        updated_at=now,
    )
    submission.status = "REVIEWED"

    db.add(review)
    db.commit()
    db.refresh(review)

    faculty_account = db.get(AuthAccount, account.id)
    _dispatch_marks_notification(
        project_id=project_id,
        submission=submission,
        review=review,
        account=account,
        db=db,
    )
    return _serialize_review(review, faculty_account)


@router.get(
    "/",
    response_model=list[ReviewResponse],
    dependencies=[Depends(require_project_access)],
)
def list_submission_reviews(
    project_id: int,
    submission_id: int,
    db: Session = Depends(get_db),
):
    _get_submission_or_404(project_id, submission_id, db)

    reviews = (
        db.query(SubmissionReview)
        .filter_by(submission_id=submission_id, project_id=project_id)
        .order_by(SubmissionReview.created_at.desc())
        .all()
    )
    return [_serialize_review(review) for review in reviews]


@router.get(
    "/{review_id}",
    response_model=ReviewResponse,
    dependencies=[Depends(require_project_access)],
)
def get_review(
    project_id: int,
    submission_id: int,
    review_id: int,
    db: Session = Depends(get_db),
):
    _get_submission_or_404(project_id, submission_id, db)

    review = (
        db.query(SubmissionReview)
        .filter_by(
            id=review_id,
            submission_id=submission_id,
            project_id=project_id,
        )
        .first()
    )
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found.",
        )
    return _serialize_review(review)


@router.put(
    "/{review_id}",
    response_model=ReviewResponse,
)
def update_review(
    project_id: int,
    submission_id: int,
    review_id: int,
    data: ReviewUpdate,
    account: Principal = Depends(require_faculty_project),
    db: Session = Depends(get_db),
):
    submission = _get_submission_or_404(project_id, submission_id, db)

    review = (
        db.query(SubmissionReview)
        .filter_by(
            id=review_id,
            submission_id=submission_id,
            project_id=project_id,
        )
        .first()
    )
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found.",
        )

    # Policy: Only the original faculty reviewer can edit their review.
    if review.faculty_account_id != account.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to edit another faculty member's review.",
        )

    cleaned_feedback = data.feedback.strip()
    if not cleaned_feedback:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Feedback must contain non-whitespace text.",
        )

    score_changed = (review.score != data.score)
    feedback_changed = (review.feedback != cleaned_feedback)

    review.score = data.score
    review.feedback = cleaned_feedback
    review.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(review)

    if score_changed or feedback_changed:
        _dispatch_marks_notification(
            project_id=project_id,
            submission=submission,
            review=review,
            account=account,
            db=db,
        )
    else:
        logger.info(
            "Review %s updated with identical score and feedback; skipping n8n notification.",
            review.id,
        )

    faculty_account = db.get(AuthAccount, account.id)
    return _serialize_review(review, faculty_account)


@router.delete(
    "/{review_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_review(
    project_id: int,
    submission_id: int,
    review_id: int,
    account: Principal = Depends(require_faculty_project),
    db: Session = Depends(get_db),
):
    _get_submission_or_404(project_id, submission_id, db)

    review = (
        db.query(SubmissionReview)
        .filter_by(
            id=review_id,
            submission_id=submission_id,
            project_id=project_id,
        )
        .first()
    )
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found.",
        )

    # Policy: Only the original faculty reviewer can delete their review.
    if review.faculty_account_id != account.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to delete another faculty member's review.",
        )

    db.delete(review)
    db.commit()
