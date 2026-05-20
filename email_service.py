"""Send transactional email (OTP) via SMTP."""
import logging
import smtplib
from email.mime.text import MIMEText

from config import Config

logger = logging.getLogger(__name__)


def send_otp_email(to_email: str, otp_code: str) -> None:
    """Send a one-time code to the address. Raises on failure."""
    subject = "Your Meal Planner verification code"
    body = (
        f"Your verification code is: {otp_code}\n\n"
        "It expires in 10 minutes. If you did not request this, ignore this email.\n\n"
        "— Meal Planner"
    )

    if Config.SIGNUP_OTP_EMAIL_ONLY:
        if not Config.smtp_configured():
            raise ValueError(
                "Sign-up is configured to send codes by email only. Set SMTP_HOST, SMTP_FROM, "
                "and your mail credentials in .env. (For local testing without mail, set "
                "SIGNUP_OTP_EMAIL_ONLY=false — not recommended for production.)"
            )
    elif Config.PRINT_OTP_TO_CONSOLE:
        logger.debug("Dev OTP for %s (not emailed; SIGNUP_OTP_EMAIL_ONLY=false)", to_email)
        return

    if not Config.smtp_configured():
        raise ValueError(
            "Email is not configured. Set SMTP_HOST, SMTP_FROM, and mail credentials in .env, "
            "or set PRINT_OTP_TO_CONSOLE=true with SIGNUP_OTP_EMAIL_ONLY=false for development only."
        )

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = Config.SMTP_FROM
    msg["To"] = to_email

    if Config.SMTP_USE_SSL:
        with smtplib.SMTP_SSL(Config.SMTP_HOST, Config.SMTP_PORT) as server:
            if Config.SMTP_USER:
                server.login(Config.SMTP_USER, Config.SMTP_PASSWORD or "")
            server.sendmail(Config.SMTP_FROM, [to_email], msg.as_string())
    else:
        with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT) as server:
            if Config.SMTP_USE_TLS:
                server.starttls()
            if Config.SMTP_USER:
                server.login(Config.SMTP_USER, Config.SMTP_PASSWORD or "")
            server.sendmail(Config.SMTP_FROM, [to_email], msg.as_string())
