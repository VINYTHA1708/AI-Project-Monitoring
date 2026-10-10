import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import settings

SMTP_TIMEOUT_SECONDS = 15


class EmailServiceError(RuntimeError):
    """Raised when the OTP email cannot be configured or delivered."""


def send_otp_email(recipient_email: str, otp: str) -> None:
    """Send an OTP using Gmail SMTP with STARTTLS.

    OTP values are included only in the email body and are never logged or placed
    in exception messages.
    """
    host = settings.SMTP_HOST.strip()
    username = settings.SMTP_USERNAME
    password = settings.SMTP_PASSWORD
    sender = settings.SMTP_FROM_EMAIL
    port = settings.SMTP_PORT

    if not host or not username or not password or not sender:
        raise EmailServiceError("SMTP email service is not fully configured.")
    if not recipient_email or any(char in recipient_email for char in "\r\n"):
        raise ValueError("A valid recipient email address is required.")
    if not otp or any(char in otp for char in "\r\n"):
        raise ValueError("A valid OTP value is required.")
    if any(char in sender for char in "\r\n"):
        raise EmailServiceError("SMTP sender configuration is invalid.")

    message = EmailMessage()
    message["Subject"] = "Your project monitoring verification code"
    message["From"] = sender
    message["To"] = recipient_email
    message.set_content(
        f"Your verification code is {otp}.\n"
        "If you did not request this code, you can ignore this email."
    )

    try:
        with smtplib.SMTP(
            host,
            port,
            timeout=SMTP_TIMEOUT_SECONDS,
        ) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
            smtp.login(username, password)
            smtp.send_message(message)
    except (smtplib.SMTPException, OSError, TimeoutError):
        raise EmailServiceError(
            "Unable to send the verification email. Check SMTP configuration "
            "and connectivity."
        ) from None
