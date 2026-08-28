from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from ..config import config
from ..database import get_db
from ..deps import COOKIE_REFRESH, get_current_user, get_user_branch_ids, get_user_roles_in_branch
from ..models import Applicant, Branch, Organization, Role, User, UserRole, UserStatus
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
