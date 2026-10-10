from datetime import datetime, date, timezone
from uuid import UUID
from sqlalchemy import (
    String,
    Text,
    DateTime,
    Date,
    ForeignKey,
    Integer,
    Boolean,
    JSON,
    CheckConstraint,
    Index,
    Uuid,
    text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    registration_number: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    auth_account: Mapped["AuthAccount | None"] = relationship(
        back_populates="student",
        uselist=False,
    )


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    github_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), default="ACTIVE", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )


class ProjectMember(Base):
    __tablename__ = "project_members"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(
        String(50), default="MEMBER", nullable=False
    )


class Milestone(Base):
    __tablename__ = "milestones"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), default="PENDING", nullable=False
    )
    completed: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)
    report_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    presentation_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    srs_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(30), default="SUBMITTED", nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    document_analyses: Mapped[list["DocumentAnalysis"]] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
    )


class DocumentAnalysis(Base):
    """Persist the latest rule-based analysis for each submission/document type.

    Only one analysis row is kept for each submission and document type. This avoids
    stale duplicate rows and keeps the most recent result authoritative for the
    corresponding submission artifact.
    """

    __tablename__ = "document_analysis"
    __table_args__ = (
        UniqueConstraint(
            "submission_id",
            "document_type",
            name="uq_document_analysis_submission_document_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="report"
    )
    analysis_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending"
    )
    completeness_percentage: Mapped[float | None] = mapped_column(
        nullable=True
    )
    detected_sections: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True
    )
    missing_sections: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True
    )
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    warnings: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    extraction_errors: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True
    )
    analyzed_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    submission: Mapped[Submission] = relationship(
        back_populates="document_analyses"
    )


class AuthAccount(Base):
    __tablename__ = "auth_accounts"
    __table_args__ = (
        CheckConstraint("role IN ('student', 'faculty')", name="ck_auth_accounts_role"),
        CheckConstraint(
            "email <> '' AND email = lower(trim(email))",
            name="ck_auth_accounts_email_normalized",
        ),
        CheckConstraint(
            "password_hash LIKE '$argon2id$%'",
            name="ck_auth_accounts_argon2id_hash",
        ),
        CheckConstraint(
            "failed_login_count >= 0",
            name="ck_auth_accounts_login_attempts",
        ),
        CheckConstraint(
            "(role = 'student' AND student_id IS NOT NULL AND faculty_id IS NULL "
            "AND faculty_name IS NULL AND phone IS NOT NULL AND trim(phone) <> '' "
            "AND department IS NOT NULL AND trim(department) <> '' "
            "AND faculty_approved = FALSE) OR "
            "(role = 'faculty' AND student_id IS NULL AND faculty_id IS NOT NULL "
            "AND trim(faculty_id) <> '' AND faculty_name IS NOT NULL "
            "AND trim(faculty_name) <> '')",
            name="ck_auth_accounts_role_profile",
        ),
        CheckConstraint(
            "NOT faculty_approved OR (role = 'faculty' AND email_verified)",
            name="ck_auth_accounts_approval_state",
        ),
        UniqueConstraint("student_id", name="uq_auth_accounts_student"),
        Index(
            "uq_auth_accounts_email_lower",
            text("lower(email)"),
            unique=True,
        ),
        Index(
            "uq_auth_accounts_faculty_id",
            text("lower(faculty_id)"),
            unique=True,
            postgresql_where=text("role = 'faculty'"),
            sqlite_where=text("role = 'faculty'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    student_id: Mapped[int | None] = mapped_column(
        ForeignKey("students.id", ondelete="RESTRICT"),
        nullable=True,
    )
    faculty_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    faculty_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    department: Mapped[str | None] = mapped_column(String(150), nullable=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    faculty_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    student: Mapped[Student | None] = relationship(back_populates="auth_account")
    otp_challenges: Mapped[list["AuthOTPChallenge"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
    )


class AuthOTPChallenge(Base):
    __tablename__ = "auth_otp_challenges"
    __table_args__ = (
        CheckConstraint(
            "purpose IN ('registration', 'login')",
            name="ck_auth_otp_challenges_purpose",
        ),
        CheckConstraint(
            "length(code_digest) = 64",
            name="ck_auth_otp_challenges_digest",
        ),
        CheckConstraint(
            "code_digest ~ '^[0-9a-f]{64}$'",
            name="ck_auth_otp_challenges_digest_hex",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "code_digest NOT GLOB '*[^0-9a-f]*'",
            name="ck_auth_otp_challenges_digest_hex",
        ).ddl_if(dialect="sqlite"),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_auth_otp_challenges_attempts",
        ),
        CheckConstraint(
            "delivery_status IN ('pending', 'delivered', 'failed', 'superseded')",
            name="ck_auth_otp_challenges_delivery_status",
        ),
        CheckConstraint(
            "(delivery_status = 'delivered') = (delivered_at IS NOT NULL)",
            name="ck_auth_otp_challenges_delivered_at",
        ),
        CheckConstraint(
            "delivery_status <> 'pending' OR consumed_at IS NULL",
            name="ck_auth_otp_challenges_pending_unconsumed",
        ),
        CheckConstraint(
            "delivery_status NOT IN ('failed', 'superseded') "
            "OR consumed_at IS NOT NULL",
            name="ck_auth_otp_challenges_terminal_consumed",
        ),
        CheckConstraint(
            "expires_at > created_at",
            name="ck_auth_otp_challenges_expiry",
        ),
        CheckConstraint(
            "consumed_at IS NULL OR consumed_at >= created_at",
            name="ck_auth_otp_challenges_consumed_time",
        ),
        Index(
            "ix_auth_otp_account_purpose_created",
            "account_id",
            "purpose",
            text("created_at DESC"),
        ),
        Index(
            "uq_auth_otp_one_unconsumed_challenge",
            "account_id",
            "purpose",
            unique=True,
            postgresql_where=text("consumed_at IS NULL"),
            sqlite_where=text("consumed_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("auth_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    purpose: Mapped[str] = mapped_column(String(24), nullable=False)
    code_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    delivery_status: Mapped[str] = mapped_column(
        String(16),
        default="pending",
        server_default=text("'pending'"),
        nullable=False,
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    account: Mapped[AuthAccount] = relationship(back_populates="otp_challenges")


class AuthRateLimitBucket(Base):
    __tablename__ = "auth_rate_limit_buckets"
    __table_args__ = (
        CheckConstraint(
            "action IN ('login', 'registration', 'verify', 'resend')",
            name="ck_auth_rate_limit_action",
        ),
        CheckConstraint(
            "scope IN ('email', 'ip')",
            name="ck_auth_rate_limit_scope",
        ),
        CheckConstraint(
            "length(subject_digest) = 64",
            name="ck_auth_rate_limit_digest",
        ),
        CheckConstraint(
            "hit_count > 0",
            name="ck_auth_rate_limit_hits",
        ),
        CheckConstraint(
            "expires_at > window_started_at",
            name="ck_auth_rate_limit_expiry",
        ),
        CheckConstraint(
            "subject_digest ~ '^[0-9a-f]{64}$'",
            name="ck_auth_rate_limit_digest_hex",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "subject_digest NOT GLOB '*[^0-9a-f]*'",
            name="ck_auth_rate_limit_digest_hex",
        ).ddl_if(dialect="sqlite"),
        Index("ix_auth_rate_limit_expiry", "expires_at"),
    )

    action: Mapped[str] = mapped_column(String(24), primary_key=True)
    scope: Mapped[str] = mapped_column(String(8), primary_key=True)
    subject_digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False)


class FacultyProjectAssignment(Base):
    __tablename__ = "faculty_project_assignments"
    __table_args__ = (
        Index(
            "ix_faculty_project_assignments_project",
            "project_id",
        ),
    )

    faculty_account_id: Mapped[int] = mapped_column(
        ForeignKey("auth_accounts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
