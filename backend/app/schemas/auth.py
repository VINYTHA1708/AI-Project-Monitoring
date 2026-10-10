from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints


Password = Annotated[str, StringConstraints(min_length=12, max_length=128)]


class StudentRegistration(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    registration_number: str = Field(min_length=1, max_length=50)
    email: EmailStr
    phone: str = Field(min_length=1, max_length=32)
    department: str = Field(min_length=1, max_length=150)
    password: Password

    model_config = ConfigDict(str_strip_whitespace=True)


class FacultyRegistration(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    faculty_id: str = Field(min_length=1, max_length=50)
    email: EmailStr
    password: Password
    department: str | None = Field(default=None, max_length=150)

    model_config = ConfigDict(str_strip_whitespace=True)


class LoginRequest(BaseModel):
    email: EmailStr
    password: Password


class OTPVerification(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r"^\d{6}$")
    purpose: Literal["registration", "login"]


class OTPResendRequest(BaseModel):
    email: EmailStr
    purpose: Literal["registration", "login"]


class RegistrationResponse(BaseModel):
    message: str
    email: EmailStr
    email_verification_required: bool = True


class LoginChallengeResponse(BaseModel):
    message: str
    email: EmailStr
    otp_verification_required: bool = True


class AuthAccountResponse(BaseModel):
    id: int
    role: Literal["student", "faculty"]
    email: EmailStr
    name: str
    student_id: int | None = None
    faculty_id: str | None = None
    department: str | None = None


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    account: AuthAccountResponse


class OTPVerificationResponse(BaseModel):
    message: str
    email_verified: bool
    faculty_approval_pending: bool = False
    access_token: str | None = None
    token_type: str | None = None
    expires_in: int | None = None
    account: AuthAccountResponse | None = None
