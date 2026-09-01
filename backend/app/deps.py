from datetime import datetime

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, UserRole, Role
from .security import decode_token

COOKIE_REFRESH = "va_refresh_token"


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = _extract_token(request)
    if not token:
        return None
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        return None
    user = db.get(User, int(payload["sub"]))
    return user


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication credentials were not provided.")
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Given token not valid for any token type")
    user = db.get(User, int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def get_user_branch_ids(user: User, db: Session) -> list[int]:
    rows = db.query(UserRole.branch_id).filter(UserRole.user_id == user.id).all()
    return sorted({r[0] for r in rows})


def get_user_roles_in_branch(user: User, branch_id: int, db: Session) -> list[str]:
    rows = (
        db.query(Role.code_name)
        .join(UserRole, UserRole.role_id == Role.id)
        .filter(UserRole.user_id == user.id, UserRole.branch_id == branch_id)
        .all()
    )
    return [r[0] for r in rows]


ROLE_PERMISSIONS = {
    "branch_admin": {"*"},
    "organization_admin": {"*"},
    "investment_manager": {
        "dashboard.view", "dealflow.view", "dealflow.edit", "approval.view", "approval.decide",
        "portfolio.view", "portfolio.edit", "reports.view", "reports.export",
        "programs.view", "selections.view", "forms.view", "courses.view", "library.view",
        "announcements.view", "calendar.view", "directories.view", "chat.use", "programs.edit",
        "disbursements.view", "disbursements.create", "disbursements.edit", "disbursements.confirm",
    },
    "mentor": {
        "dashboard.view", "programs.view", "courses.view", "library.view", "announcements.view",
        "calendar.view", "directories.view", "chat.use", "applicants.score", "mentor.review",
    },
    "entrepreneur": {
        "courses.view", "announcements.view", "calendar.view", "chat.use", "library.view",
        "programs.view",
    },
}

SUPER_ROLES = {"*", "branch_admin", "organization_admin"}


def has_perm(user_roles: list[str], perm: str) -> bool:
    for role in user_roles:
        perms = ROLE_PERMISSIONS.get(role, set())
        if "*" in perms or perm in perms:
            return True
    return False


def check_user_perm_in_branch(user: User, branch_id: int, roles: list[str], perm: str, db: Session) -> bool:
    if has_perm(roles, perm):
        return True
    # Check custom role permissions from DB
    db_roles = (
        db.query(Role)
        .join(UserRole, UserRole.role_id == Role.id)
        .filter(UserRole.user_id == user.id, UserRole.branch_id == branch_id)
        .all()
    )
    for r in db_roles:
        role_perms = r.permissions or []
        if "*" in role_perms or perm in role_perms:
            return True
    return False


def require_branch_access(branch_id_param: str = "branch_id"):
    """Dependency factory: resolves the branch from the path/query and enforces tenant isolation."""

    def dependency(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
        branch_id = request.path_params.get(branch_id_param) or request.query_params.get("branch_id")
        if branch_id is None:
            raise HTTPException(status_code=400, detail="Branch id is required.")
        try:
            branch_id = int(branch_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid branch id.")
        allowed = get_user_branch_ids(user, db)
        if branch_id not in allowed:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to perform this action.",
            )
        roles = get_user_roles_in_branch(user, branch_id, db)
        return {"user": user, "branch_id": branch_id, "roles": roles, "db": db}

    return dependency


def require_perm(perm: str):
    def dependency(ctx=Depends(require_branch_access())):
        if not check_user_perm_in_branch(ctx["user"], ctx["branch_id"], ctx["roles"], perm, ctx["db"]):
            raise HTTPException(status_code=403, detail="You do not have permission to perform this action.")
        return ctx

    return dependency
