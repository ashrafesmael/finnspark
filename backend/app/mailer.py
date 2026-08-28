"""Minimal SMTP email sender. Activates only when SMTP_HOST + SMTP_FROM are configured."""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .config import config

logger = logging.getLogger(__name__)


def send_email(to: str, subject: str, html: str) -> bool:
    """Returns True if sent, False if SMTP is not configured or delivery failed."""
    if not config.smtp_enabled:
        logger.info("SMTP not configured - email to %s skipped (%s)", to, subject)
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = config.SMTP_FROM
        msg["To"] = to
        msg.attach(MIMEText(html, "html", "utf-8"))
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as s:
            if config.SMTP_TLS:
                s.starttls()
            if config.SMTP_USER:
                s.login(config.SMTP_USER, config.SMTP_PASSWORD)
            s.sendmail(config.SMTP_FROM, [to], msg.as_string())
        logger.info("email sent to %s (%s)", to, subject)
        return True
    except Exception:
        logger.exception("failed to send email to %s", to)
        return False


def invite_email_html(name: str, link: str) -> str:
    return (
        '<div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto">'
        '<h2 style="color:#1d6f5c">Welcome to finnspark</h2>'
        f"<p>Hello {name or 'there'},</p>"
        "<p>Your application has moved forward! Click the button below to create your "
        "founder account (the link is valid for <b>14 days</b>):</p>"
        f'<p style="text-align:center;margin:28px 0">'
        f'<a href="{link}" style="background:#1d6f5c;color:#fff;padding:12px 28px;'
        'border-radius:6px;text-decoration:none;font-weight:bold">Create my account</a></p>'
        '<p style="color:#666;font-size:13px">Or copy this link into your browser:<br>'
        f'<a href="{link}">{link}</a></p>'
        '<p style="color:#666;font-size:13px">If you weren\'t expecting this email, '
        "you can ignore it.</p></div>"
    )
