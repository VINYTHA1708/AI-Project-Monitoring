from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str

    APP_ENV: str = "development"
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM_EMAIL: str | None = None

    GROQ_API_KEY: str | None = None
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    STUDENT_EMAIL_DOMAINS: str = ""
    FACULTY_EMAIL_ALLOWLIST: str = ""
    JWT_SECRET_KEY: str | None = None
    OTP_HMAC_SECRET: str | None = None
    AUTH_TOKEN_ISSUER: str = "ai-project-monitoring"
    AUTH_TOKEN_AUDIENCE: str = "ai-project-monitoring-api"
    AUTH_TOKEN_LIFETIME_MINUTES: int = Field(default=30, gt=0, le=1440)
    AUTH_OTP_LIFETIME_SECONDS: int = Field(default=600, gt=0, le=86400)
    AUTH_OTP_MAX_ATTEMPTS: int = Field(default=5, gt=0, le=20)
    AUTH_OTP_RESEND_COOLDOWN_SECONDS: int = Field(default=60, ge=0, le=3600)
    AUTH_OTP_MAX_SENDS_PER_HOUR: int = Field(default=5, gt=0, le=20)
    AUTH_LOGIN_MAX_ATTEMPTS: int = Field(default=5, gt=0, le=20)
    AUTH_LOGIN_LOCKOUT_SECONDS: int = Field(default=900, gt=0, le=86400)
    AUTH_RATE_LIMIT_AUTH_WINDOW_SECONDS: int = Field(default=900, gt=0, le=86400)
    AUTH_RATE_LIMIT_REGISTRATION_WINDOW_SECONDS: int = Field(
        default=3600, gt=0, le=86400
    )
    AUTH_RATE_LIMIT_RESEND_WINDOW_SECONDS: int = Field(
        default=3600, gt=0, le=86400
    )
    AUTH_RATE_LIMIT_LOGIN_EMAIL_MAX: int = Field(default=10, gt=0, le=1000)
    AUTH_RATE_LIMIT_LOGIN_IP_MAX: int = Field(default=60, gt=0, le=10000)
    AUTH_RATE_LIMIT_REGISTRATION_EMAIL_MAX: int = Field(default=3, gt=0, le=1000)
    AUTH_RATE_LIMIT_REGISTRATION_IP_MAX: int = Field(default=10, gt=0, le=10000)
    AUTH_RATE_LIMIT_VERIFY_EMAIL_MAX: int = Field(default=10, gt=0, le=1000)
    AUTH_RATE_LIMIT_VERIFY_IP_MAX: int = Field(default=60, gt=0, le=10000)
    AUTH_RATE_LIMIT_RESEND_EMAIL_MAX: int = Field(default=5, gt=0, le=1000)
    AUTH_RATE_LIMIT_RESEND_IP_MAX: int = Field(default=20, gt=0, le=10000)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    @property
    def student_email_domains(self) -> set[str]:
        return {
            domain.strip().lower().lstrip("@")
            for domain in self.STUDENT_EMAIL_DOMAINS.split(",")
            if domain.strip()
        }

    @property
    def faculty_email_allowlist(self) -> set[str]:
        return {
            email.strip().lower()
            for email in self.FACULTY_EMAIL_ALLOWLIST.split(",")
            if email.strip()
        }

    def validate_production_auth_settings(self) -> None:
        if self.APP_ENV.strip().lower() not in {"production", "prod"}:
            return

        for name, value in (
            ("JWT_SECRET_KEY", self.JWT_SECRET_KEY),
            ("OTP_HMAC_SECRET", self.OTP_HMAC_SECRET),
        ):
            if (
                not value
                or len(value.encode("utf-8")) < 32
                or value.strip().lower().startswith(
                    ("your-", "change-me", "changeme", "replace-with-")
                )
            ):
                raise ValueError(
                    f"{name} must be configured with a unique secret of at least 32 bytes."
                )

        if not self.student_email_domains or not self.faculty_email_allowlist:
            raise ValueError(
                "Production requires student email domains and a faculty email allowlist."
            )
        if self.JWT_SECRET_KEY == self.OTP_HMAC_SECRET:
            raise ValueError("JWT_SECRET_KEY and OTP_HMAC_SECRET must be different.")


settings = Settings()
