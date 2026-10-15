import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_SMTP_TIMEOUT_SECONDS = 30


class EmailServiceError(RuntimeError):
    """Raised when the OTP email cannot be configured or delivered."""


def send_otp_email(recipient_email: str, otp: str) -> None:
    """Send an OTP email using SMTP with STARTTLS (e.g. port 587) or SSL (e.g. port 465).

    OTP values are included only in the email body and are never logged or placed
    in exception messages. Passwords and credentials are never logged.
    """
    host = (settings.SMTP_HOST or "").strip()
    username = (settings.SMTP_USERNAME or "").strip()
    password = settings.SMTP_PASSWORD
    sender = (settings.SMTP_FROM_EMAIL or "").strip()
    port = settings.SMTP_PORT
    timeout = getattr(settings, "SMTP_TIMEOUT_SECONDS", DEFAULT_SMTP_TIMEOUT_SECONDS) or DEFAULT_SMTP_TIMEOUT_SECONDS

    # 1. Check for missing configuration
    missing_vars: list[str] = []
    if not host:
        missing_vars.append("SMTP_HOST")
    if not username:
        missing_vars.append("SMTP_USERNAME")
    if not password:
        missing_vars.append("SMTP_PASSWORD")
    if not sender:
        missing_vars.append("SMTP_FROM_EMAIL")

    if missing_vars:
        logger.error(
            "SMTP email service is not fully configured. Missing settings: %s. "
            "Please check backend/.env or your environment variables.",
            ", ".join(missing_vars),
        )
        raise EmailServiceError(
            "SMTP email service is not fully configured. Missing configuration: "
            + ", ".join(missing_vars)
        )

    # 2. Validate input strings to prevent CRLF / header injection
    if not recipient_email or any(char in recipient_email for char in "\r\n"):
        raise ValueError("A valid recipient email address is required.")
    if not otp or any(char in otp for char in "\r\n"):
        raise ValueError("A valid OTP value is required.")
    if any(char in sender for char in "\r\n"):
        logger.error("SMTP sender address contains invalid control characters.")
        raise EmailServiceError("SMTP sender configuration is invalid.")

    message = EmailMessage()
    message["Subject"] = "Your project monitoring verification code"
    message["From"] = sender
    message["To"] = recipient_email
    message.set_content(
        f"Your verification code is {otp}.\n"
        "If you did not request this code, you can ignore this email."
    )

    context = ssl.create_default_context()

    try:
        if port == 465:
            logger.info("Connecting to SMTP server at %s:%d using SSL (timeout=%ss)", host, port, timeout)
            with smtplib.SMTP_SSL(host, port, context=context, timeout=timeout) as smtp:
                smtp.ehlo()
                smtp.login(username, password)
                smtp.send_message(message)
        else:
            logger.info("Connecting to SMTP server at %s:%d using STARTTLS (timeout=%ss)", host, port, timeout)
            with smtplib.SMTP(host, port, timeout=timeout) as smtp:
                smtp.ehlo()
                smtp.starttls(context=context)
                smtp.ehlo()
                smtp.login(username, password)
                smtp.send_message(message)
        logger.info("OTP verification email delivered to SMTP server successfully.")
    except smtplib.SMTPAuthenticationError as exc:
        code = getattr(exc, "smtp_code", None) or "auth_failed"
        logger.error(
            "SMTP authentication failed on %s:%d (code=%s). Check that SMTP_USERNAME and SMTP_PASSWORD are correct.",
            host,
            port,
            code,
        )
        raise EmailServiceError(
            "SMTP authentication failed. Verify SMTP username and password."
        ) from None
    except smtplib.SMTPServerDisconnected as exc:
        logger.error(
            "SMTP server unexpectedly disconnected on %s:%d: %s",
            host,
            port,
            type(exc).__name__,
        )
        raise EmailServiceError(
            "SMTP server disconnected. Check host, port, and network connection."
        ) from None
    except smtplib.SMTPRecipientsRefused as exc:
        logger.error(
            "SMTP server rejected the recipient on %s:%d (refused_count=%d)",
            host,
            port,
            len(getattr(exc, "recipients", {})),
        )
        raise EmailServiceError(
            "Recipient email address was rejected by the SMTP server."
        ) from None
    except (TimeoutError, smtplib.SMTPConnectError) as exc:
        logger.error(
            "SMTP connection to %s:%d timed out or failed to connect: %s",
            host,
            port,
            type(exc).__name__,
        )
        raise EmailServiceError(
            "SMTP connection timed out or failed to connect. Check SMTP host, port, and network connectivity."
        ) from None
    except (smtplib.SMTPException, OSError) as exc:
        logger.error(
            "SMTP delivery failure on %s:%d (%s): %s",
            host,
            port,
            type(exc).__name__,
            str(exc),
        )
        raise EmailServiceError(
            "Unable to send the verification email. Check SMTP configuration and connectivity."
        ) from None
