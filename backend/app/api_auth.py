from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import Principal, get_current_account, get_db
from app.auth.rate_limit import enforce_auth_rate_limit
from app.auth.service import (
    AuthServiceError,
    account_response,
    begin_login,
    register_faculty,
    register_student,
    resend_otp,
    verify_otp,
)
from app.db.models import AuthAccount
from app.schemas.auth import (
    AuthAccountResponse,
    LoginChallengeResponse,
    LoginRequest,
    OTPResendRequest,
    OTPVerification,
    OTPVerificationResponse,
    RegistrationResponse,
    StudentRegistration,
    FacultyRegistration,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _run(operation, *args):
    try:
        return operation(*args)
    except AuthServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/register/student", response_model=RegistrationResponse, status_code=202)
def student_registration(
    data: StudentRegistration,
    request: Request,
    db: Session = Depends(get_db),
):
    _run(
        enforce_auth_rate_limit,
        "registration",
        str(data.email),
        request.client.host if request.client else None,
        db,
    )
    _run(register_student, data, db)
    return {
        "message": "If eligible, an email verification code has been sent.",
        "email": str(data.email).strip().lower(),
    }


@router.post("/register/faculty", response_model=RegistrationResponse, status_code=202)
def faculty_registration(
    data: FacultyRegistration,
    request: Request,
    db: Session = Depends(get_db),
):
    _run(
        enforce_auth_rate_limit,
        "registration",
        str(data.email),
        request.client.host if request.client else None,
        db,
    )
    _run(register_faculty, data, db)
    return {
        "message": "If eligible, an email verification code has been sent.",
        "email": str(data.email).strip().lower(),
    }


@router.post("/login", response_model=LoginChallengeResponse, status_code=202)
def login(data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    _run(
        enforce_auth_rate_limit,
        "login",
        str(data.email),
        request.client.host if request.client else None,
        db,
    )
    _run(begin_login, str(data.email), data.password, db)
    return {
        "message": "If eligible, a sign-in verification code has been sent.",
        "email": str(data.email).strip().lower(),
    }


@router.post("/otp/resend", status_code=202)
def resend_verification_code(
    data: OTPResendRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    _run(
        enforce_auth_rate_limit,
        "resend",
        str(data.email),
        request.client.host if request.client else None,
        db,
    )
    _run(resend_otp, str(data.email), data.purpose, db)
    return {"message": "If the account and request are eligible, a code has been sent."}


@router.post("/otp/verify", response_model=OTPVerificationResponse)
def verify_verification_code(
    data: OTPVerification,
    request: Request,
    db: Session = Depends(get_db),
):
    _run(
        enforce_auth_rate_limit,
        "verify",
        str(data.email),
        request.client.host if request.client else None,
        db,
    )
    return _run(
        verify_otp,
        str(data.email),
        data.code,
        data.purpose,
        db,
    )


@router.get("/me", response_model=AuthAccountResponse)
def get_my_account(
    principal: Principal = Depends(get_current_account),
    db: Session = Depends(get_db),
):
    account = db.scalar(
        select(AuthAccount).where(AuthAccount.id == principal.id)
    )
    if account is None:
        raise HTTPException(status_code=401, detail="Authentication is required.")
    return account_response(account)
