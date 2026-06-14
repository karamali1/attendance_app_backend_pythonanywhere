import os
import smtplib
from email.message import EmailMessage


MAIL_USERNAME = os.getenv("MAIL_USERNAME")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
MAIL_FROM = os.getenv("MAIL_FROM", MAIL_USERNAME)
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000")


def build_verification_link(token: str) -> str:
    return f"{APP_BASE_URL}/verify-email?token={token}"


def send_verification_email(to_email: str, full_name: str, token: str) -> None:
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        raise ValueError("Email settings are missing. Set MAIL_USERNAME and MAIL_PASSWORD.")

    verification_link = build_verification_link(token)

    msg = EmailMessage()
    msg["Subject"] = "Verify your Attendance App email"
    msg["From"] = MAIL_FROM
    msg["To"] = to_email

    msg.set_content(
        f"""
Hello {full_name},

Thank you for registering in the Attendance App.

Please verify your email by clicking this link:
{verification_link}

If you did not create this account, you can ignore this email.
""".strip()
    )

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(MAIL_USERNAME, MAIL_PASSWORD)
        smtp.send_message(msg)