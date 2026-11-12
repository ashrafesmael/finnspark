from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from ..config import config
from ..database import get_db
from ..deps import COOKIE_REFRESH, get_current_user, get_user_branch_ids, get_user_roles_in_branch
from ..models import Applicant, AuthToken, Branch, Organization, Role, User, UserRole, UserStatus
from ..security import create_token, decode_token, hash_password, verify_password

router = APIRouter(tags=["auth"])


def user_blob(user: User, db: Session) -> dict:
    status = db.get(UserStatus, user.status_id) if user.status_id else None
    branches = []
    for bid in get_user_branch_ids(user, db):
        branch = db.get(Branch, bid)
        if not branch:
            continue
        org = db.get(Organization, branch.organization_id)
        branches.append({
            "id": branch.id,
            "name": branch.name,
            "organization_id": branch.organization_id,
            "organization_name": org.name if org else "",
            "roles": get_user_roles_in_branch(user, bid, db),
        })
    return {
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "photo": user.photo,
        "position": user.position,
        "status": {"id": status.id, "name": status.name, "code_name": status.code_name} if status else None,
        "branches": branches,
    }


def _is_secure(request: Request) -> bool:
    """True when the request arrived over TLS (directly or via nginx X-Forwarded-Proto)."""
    return request.url.scheme == "https" or \
        request.headers.get("x-forwarded-proto", "").lower() == "https"


def _issue(response: Response, user: User, db: Session, request: Request):
    branch_ids = get_user_branch_ids(user, db)
    roles = get_user_roles_in_branch(user, branch_ids[0], db) if branch_ids else []
    access = create_token(user.id, branch_ids[0] if branch_ids else None, roles, "access")
    refresh = create_token(user.id, None, [], "refresh")
    response.set_cookie(
        COOKIE_REFRESH, refresh,
        httponly=True,
        # Secure cookies are dropped by browsers on plain HTTP — only enable behind TLS
        secure=_is_secure(request),
        samesite="lax",
        # "/" so the cookie applies whether the SPA calls /auth/refresh or /api/auth/refresh
        max_age=config.REFRESH_TOKEN_DAYS * 86400, path="/",
    )
    return access


class LoginIn(BaseModel):
    email: str
    password: str


@router.post("/login/")
def login(data: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email.strip().lower()).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="No active account found with the given credentials")
    code = db.get(UserStatus, user.status_id).code_name if user.status_id else "active"
    if code == "pending":
        raise HTTPException(status_code=403,
                            detail="Your registration is awaiting administrator approval. "
                                   "You will receive an email with an activation link once approved.")
    if code in ("suspended", "inactive"):
        raise HTTPException(status_code=403, detail="This account is not active. Please contact an administrator.")
    access = _issue(response, user, db, request)
    return {"access_token": access, "token_type": "bearer", "user": user_blob(user, db)}


@router.post("/refresh/")
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(COOKIE_REFRESH)
    if not token:
        raise HTTPException(status_code=401, detail="Refresh token missing")
    payload = decode_token(token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Refresh token invalid or expired")
    user = db.get(User, int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    access = _issue(response, user, db, request)
    return {"access_token": access, "token_type": "bearer"}


@router.post("/logout/")
def logout(response: Response):
    response.delete_cookie(COOKIE_REFRESH, path="/")
    return {"detail": "Logged out"}


@router.get("/me/")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return user_blob(user, db)


class RegisterIn(BaseModel):
    password: str
    first_name: str = ""
    last_name: str = ""
    token: str  # invitation token from "Invite founder to register"


def _invite_applicant(token: str, db: Session) -> Applicant:
    from ..security import decode_token
    payload = decode_token(token)
    if not payload or payload.get("type") != "invite":
        raise HTTPException(status_code=400, detail="Invitation link is invalid or has expired. "
                                                   "Please ask the program team to send a new one.")
    a = db.get(Applicant, int(payload["sub"]))
    if not a:
        raise HTTPException(status_code=400, detail="This invitation no longer matches an applicant.")
    if a.registered or db.query(User).filter(User.email == a.email).first():
        raise HTTPException(status_code=400, detail="An account with this email already exists — please log in.")
    return a


@router.get("/invite-info", tags=["public"])
def invite_info(token: str, db: Session = Depends(get_db)):
    """Prefill data for the registration page."""
    a = _invite_applicant(token, db)
    return {
        "email": a.email,
        "first_name": a.first_name or "",
        "last_name": a.last_name or "",
        "business_name": a.business_name or "",
        "branch_id": a.branch_id,
    }


@router.post("/register", tags=["public"])
def register(data: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)):
    a = _invite_applicant(data.token, db)
    email = a.email
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="A user with this email already exists.")
    user = User(
        email=email,
        password_hash=hash_password(data.password),
        first_name=data.first_name,
        last_name=data.last_name,
        position="Entrepreneur",
    )
    active_status = db.query(UserStatus).filter(UserStatus.code_name == "active").first()
    user.status_id = active_status.id if active_status else None
    db.add(user)
    db.flush()

    # Link any existing applicant records and mark them registered.
    applicants = db.query(Applicant).filter(Applicant.email == email).all()
    branch_ids = {a.branch_id for a in applicants}
    for a in applicants:
        a.registered = True
        a.user_id = user.id
    entrepreneur_role = (
        db.query(Role)
        .filter(Role.code_name == "entrepreneur", Role.branch_id.in_(branch_ids))
        .all()
    )
    for role in entrepreneur_role:
        db.add(UserRole(user_id=user.id, role_id=role.id, branch_id=role.branch_id))
    # If the caller asked for a branch without a seeded entrepreneur role, create one.
    missing = branch_ids - {r.branch_id for r in entrepreneur_role}
    for bid in missing:
        role = Role(branch_id=bid, name="Entrepreneur", code_name="entrepreneur", is_constant=True)
        db.add(role)
        db.flush()
        db.add(UserRole(user_id=user.id, role_id=role.id, branch_id=bid))

    db.commit()
    access = _issue(response, user, db, request)
    return {"access_token": access, "token_type": "bearer", "user": user_blob(user, db)}


# ===========================================================================
# Public account flows: self-registration, admin approval, password reset
# (adapted from the DevX auth flow: hashed single-use tokens, email-agnostic
#  forgot-password responses, auto-login on activation)
# ===========================================================================
import re
import hashlib
import secrets

from ..mailer import send_email

PUBLIC_BASE = (config.PUBLIC_BASE_URL or "https://accelerate.finnpact.com").rstrip("/")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _status_by_code(db: Session, code: str, name: str = "") -> UserStatus:
    st = db.query(UserStatus).filter(UserStatus.code_name == code).first()
    if not st:
        st = UserStatus(code_name=code, name=name or code.title())
        db.add(st)
        db.flush()
    return st


def _make_token(db: Session, user: User, purpose: str, hours: int,
                role_ids=None, branch_id=None):
    raw = secrets.token_hex(32)
    tok = AuthToken(
        token_hash=_hash_token(raw), purpose=purpose, user_id=user.id,
        email=user.email, display_name=f"{user.first_name or ''} {user.last_name or ''}".strip(),
        role_ids=role_ids or [], branch_id=branch_id,
        expires_at=datetime.utcnow() + __import__("datetime").timedelta(hours=hours),
    )
    db.add(tok)
    db.flush()
    return raw, tok


def _button_html(url, label):
    return ('<p style="text-align:center;margin:26px 0">'
            f'<a href="{url}" style="background:#174950;color:#fff;padding:12px 28px;'
            'border-radius:6px;text-decoration:none;font-weight:bold">' + label + "</a></p>")


class PublicRegisterIn(BaseModel):
    first_name: str = ""
    last_name: str = ""
    email: str


@router.post("/public-register/", tags=["public"])
def public_register(data: PublicRegisterIn, db: Session = Depends(get_db)):
    """Open self-registration: creates a PENDING account (no password) and emails
    a confirmation. An administrator then approves it — the approval email carries
    a single-use link for the user to choose a password and sign in."""
    first = (data.first_name or "").strip()
    last = (data.last_name or "").strip()
    email = (data.email or "").strip().lower()
    if len(first) < 1 and len(last) < 1:
        raise HTTPException(status_code=400, detail="Please provide your name.")
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Please provide a valid email address.")

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        code = db.get(UserStatus, existing.status_id).code_name if existing.status_id else ""
        if code == "pending":
            raise HTTPException(status_code=400,
                                detail="Your registration has already been received and is "
                                       "awaiting administrator approval.")
        raise HTTPException(status_code=400,
                            detail="An account with this email already exists. Please sign in.")

    pending = _status_by_code(db, "pending", "Pending approval")
    user = User(email=email, first_name=first, last_name=last,
                position="Entrepreneur", status_id=pending.id,
                # no password yet — a random hash nothing can match until the
                # user sets one through their activation link
                password_hash=hash_password(secrets.token_hex(32)))
    db.add(user)
    db.flush()

    confirm_url = f"{PUBLIC_BASE}/login"
    send_email(email, "Registration received — finnspark",
               f'<div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto">'
               f"<h2 style=\"color:#174950\">Welcome to finnspark</h2>"
               f"<p>Hello {first or last or 'there'},</p>"
               "<p>Thank you for registering. Your account will be activated as soon as an "
               "administrator approves it, and you will receive an email with a link to set "
               "your password.</p>"
               f'<p style="color:#666;font-size:13px">If you weren\'t expecting this email, '
               "you can ignore it.</p></div>")

    db.commit()
    return {
        "ok": True,
        "message": "Registration received. A confirmation email has been sent. "
                   "Your account will be activated once approved by the administrator.",
    }


class ForgotPasswordIn(BaseModel):
    email: str


@router.post("/forgot-password/", tags=["public"])
def forgot_password(data: ForgotPasswordIn, db: Session = Depends(get_db)):
    """Email-agnostic by design — never reveals whether an account exists."""
    email = (data.email or "").strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Please provide a valid email address.")

    user = db.query(User).filter(User.email == email).first()
    if user and (not user.status_id or
                 (db.get(UserStatus, user.status_id).code_name not in ("pending",))):
        raw, _tok = _make_token(db, user, "reset", hours=24)
        reset_url = f"{PUBLIC_BASE}/set-password?token={raw}"
        send_email(user.email, "Reset your finnspark password",
                   '<div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto">'
                   '<h2 style="color:#174950">Reset your password</h2>'
                   f"<p>Hello {user.first_name or 'there'},</p>"
                   "<p>Click the button below to choose a new password "
                   "(the link is valid for <b>24 hours</b> and can be used once):</p>"
                   + _button_html(reset_url, "Choose a new password") +
                   '<p style="color:#666;font-size:13px">Or copy this link into your browser:<br>'
                   f'<a href="{reset_url}">{reset_url}</a></p>'
                   '<p style="color:#666;font-size:13px">If you didn\'t request a reset, '
                   "you can safely ignore this email.</p></div>")
        db.commit()

    return {"ok": True,
            "message": "If an active account exists with this email address, "
                       "a password reset link has been sent."}


@router.get("/verify-token/", tags=["public"])
def verify_token(token: str = "", db: Session = Depends(get_db)):
    if not token:
        raise HTTPException(status_code=400, detail="Token is missing.")
    tok = db.query(AuthToken).filter(
        AuthToken.token_hash == _hash_token(token), AuthToken.used_at.is_(None)).first()
    if not tok or tok.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400,
                            detail="This link is invalid or has expired. Please request a new one.")
    return {"ok": True, "email": tok.email, "displayName": tok.display_name,
            "purpose": tok.purpose, "isReset": tok.purpose == "reset"}


class SetPasswordIn(BaseModel):
    token: str
    password: str


@router.post("/set-password/", tags=["public"])
def set_password(data: SetPasswordIn, request: Request, response: Response,
                 db: Session = Depends(get_db)):
    """One-stop activation: for invite tokens this also activates the account and
    assigns the stored branch roles; both flows log the user straight in."""
    if not data.token:
        raise HTTPException(status_code=400, detail="Token is missing.")
    if len(data.password or "") < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long.")

    tok = db.query(AuthToken).filter(
        AuthToken.token_hash == _hash_token(data.token), AuthToken.used_at.is_(None)).first()
    if not tok or tok.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400,
                            detail="This link is invalid or has expired. Please request a new one.")

    user = db.get(User, tok.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Account no longer exists.")

    user.password_hash = hash_password(data.password)
    active = _status_by_code(db, "active", "Active")
    user.status_id = active.id

    if tok.purpose == "invite":
        # assign the branch roles stored with the invite/approval
        for rid in (tok.role_ids or []):
            role = db.get(Role, int(rid))
            if role:
                exists = db.query(UserRole).filter_by(
                    user_id=user.id, branch_id=role.branch_id, role_id=role.id).first()
                if not exists:
                    db.add(UserRole(user_id=user.id, role_id=role.id, branch_id=role.branch_id))

    tok.used_at = datetime.utcnow()
    db.commit()
    access = _issue(response, user, db, request)
    return {"ok": True, "access_token": access, "token_type": "bearer",
            "isReset": tok.purpose == "reset", "user": user_blob(user, db)}
