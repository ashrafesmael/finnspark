"""Email sender supporting Microsoft Graph API (OAuth 2.0 app-only) with SMTP fallback."""
import logging
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx

from .config import config

logger = logging.getLogger(__name__)

_graph_tok: str | None = None
_graph_tok_exp: float = 0.0


def _get_graph_token() -> str:
    global _graph_tok, _graph_tok_exp
    if _graph_tok and time.time() < _graph_tok_exp - 60:
        return _graph_tok
    r = httpx.post(
        f"https://login.microsoftonline.com/{config.MS_GRAPH_TENANT_ID}/oauth2/v2.0/token",
        data={
            "client_id": config.MS_GRAPH_CLIENT_ID,
            "client_secret": config.MS_GRAPH_CLIENT_SECRET,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        },
        timeout=20.0,
    )
    r.raise_for_status()
    data = r.json()
    _graph_tok = data["access_token"]
    _graph_tok_exp = time.time() + int(data.get("expires_in", 3600))
    return _graph_tok


def _send_via_graph(to: str, subject: str, html: str, from_name: str = "finnspark") -> bool:
    try:
        token = _get_graph_token()
        message = {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html},
            "toRecipients": [{"emailAddress": {"address": to}}],
            "from": {"emailAddress": {"name": from_name, "address": config.MS_GRAPH_SENDER}},
        }
        r = httpx.post(
            f"https://graph.microsoft.com/v1.0/users/{config.MS_GRAPH_SENDER}/sendMail",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"message": message, "saveToSentItems": False},
            timeout=30.0,
        )
        if r.status_code in (200, 202):
            logger.info("email sent via MS Graph to %s (%s)", to, subject)
            return True
        logger.error("MS Graph sendMail failed [%s]: %s", r.status_code, r.text[:400])
        return False
    except Exception:
        logger.exception("failed to send email via MS Graph to %s", to)
        return False


def _send_via_smtp(to: str, subject: str, html: str) -> bool:
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
        logger.info("email sent via SMTP to %s (%s)", to, subject)
        return True
    except Exception:
        logger.exception("failed to send email via SMTP to %s", to)
        return False


def send_email(to: str, subject: str, html: str, from_name: str = "finnspark") -> bool:
    """Sends email via Microsoft Graph API if configured, otherwise falls back to SMTP."""
    if config.use_graph:
        return _send_via_graph(to, subject, html, from_name=from_name)
    if config.smtp_enabled:
        return _send_via_smtp(to, subject, html)
    logger.info("Email service not configured - email to %s skipped (%s)", to, subject)
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
