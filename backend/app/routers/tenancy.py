from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_user_branch_ids, require_branch_access, require_perm
from ..models import (
    Branch, Organization, OrganizationStatus, Role, User, UserRole, UserStatus,
)
from ..utils import paginate, parse_page, serialize_ref

router = APIRouter(tags=["tenancy"])


def user_row(u: User, db: Session, branch_id: int | None = None) -> dict:
    status = db.get(UserStatus, u.status_id) if u.status_id else None
    roles = []
    if branch_id:
        q = db.query(Role).join(UserRole, UserRole.role_id == Role.id).filter(
            UserRole.user_id == u.id, UserRole.branch_id == branch_id)
        roles = [{"id": r.id, "name": r.name, "code_name": r.code_name} for r in q.all()]
    return {
        "id": u.id,
        "email": u.email,
        "first_name": u.first_name,
        "last_name": u.last_name,
        "photo": u.photo,
        "position": u.position,
        "company": u.company,
        "status": serialize_ref(status) if status else None,
        "roles": roles,
    }


# ------------------------------------------------------------------ organizations

@router.get("/organizations/")
def list_organizations(db: Session = Depends(get_db), user=Depends(get_current_user),
                       status: int | None = None, search: str | None = None):
    q = db.query(Organization)
    if status:
        q = q.filter(Organization.status_id == status)
    if search:
        q = q.filter(Organization.name.ilike(f"%{search}%"))

    def ser(o):
        st = db.get(OrganizationStatus, o.status_id) if o.status_id else None
        branches = db.query(Branch).filter(Branch.organization_id == o.id).all()
        return {
            "id": o.id, "name": o.name, "registration_date": str(o.registration_date or ""),
            "status": serialize_ref(st) if st else None,
            "branches": [{"id": b.id, "name": b.name} for b in branches],
        }
    return [ser(o) for o in q.all()]


class OrganizationIn(BaseModel):
    name: str
    registration_date: str | None = None


@router.post("/organizations/")
def create_organization(data: OrganizationIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    org = Organization(name=data.name)
    st = db.query(OrganizationStatus).filter(OrganizationStatus.code_name == "active").first()
    org.status_id = st.id if st else None
    db.add(org)
    db.commit()
    db.refresh(org)
    return {"id": org.id, "name": org.name}


class BranchIn(BaseModel):
    organization_id: int
    name: str


def _require_org_admin(user, db: Session, org_id: int) -> Organization:
    """Organization admins / branch admins (platform-wide) may edit or delete organizations."""
    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Not found.")
    role_ids = [r[0] for r in db.query(UserRole.role_id).filter_by(user_id=user.id).all()]
    codes = {r[0] for r in db.query(Role.code_name).filter(Role.id.in_(role_ids or [0]))}
    if not codes & {"organization_admin", "branch_admin"}:
        raise HTTPException(status_code=403,
                            detail="You do not have permission to perform this action.")
    return org


class OrgPatch(BaseModel):
    name: str | None = None
    status: str | None = None   # code_name from /organization-statuses/


@router.patch("/organizations/{org_id}/")
def update_organization(org_id: int, data: OrgPatch, db: Session = Depends(get_db),
                        user=Depends(get_current_user)):
    org = _require_org_admin(user, db, org_id)
    if data.name:
        org.name = data.name.strip()
    if data.status:
        st = db.query(OrganizationStatus).filter(
            OrganizationStatus.code_name == data.status).first()
        if not st:
            raise HTTPException(status_code=400, detail="Invalid status.")
        org.status_id = st.id
    db.commit()
    return {"id": org.id, "name": org.name, "status_id": org.status_id}


def _delete_branch_cascade(db: Session, branch_id: int):
    """Delete a branch and every record scoped to it (single transaction)."""
    from ..models import (
        Announcement, AnnouncementReaction, Applicant, ApplicationForm, ApplicationFormField,
        ApplicationFormFieldOption, Business, BusinessFounder, CalendarEvent, Channel,
        Chat, ChatMessage, ChatParticipant, CommitteeDecision, CommitteeLevel, ContentBlock,
        Course, Document, Enrollment, Evaluation, FinanceTimelineEntry, InvestmentCase,
        InvestmentStage, Lesson, MentorConclusionQuestion, MentorReviewQuestion, Mentorship,
        Module, PaymentScheduleEntry, Program, ProgramType, ProgressRecord, QuestionAnswer,
        ScoringForm, ScoringQuestion, SelectionStage, Subindustry,
    )
    case_ids = [c[0] for c in db.query(InvestmentCase.id).filter_by(branch_id=branch_id)]
    if case_ids:
        for model in (FinanceTimelineEntry, PaymentScheduleEntry, CommitteeDecision):
            db.query(model).filter(model.case_id.in_(case_ids)).delete(synchronize_session=False)
    for model in (InvestmentCase, CommitteeLevel, InvestmentStage):
        db.query(model).filter_by(branch_id=branch_id).delete(synchronize_session=False)

    form_ids = [f[0] for f in db.query(ApplicationForm.id).filter_by(branch_id=branch_id)]
    if form_ids:
        field_ids = [f[0] for f in db.query(ApplicationFormField.id).filter(
            ApplicationFormField.application_form_id.in_(form_ids))]
        if field_ids:
            db.query(ApplicationFormFieldOption).filter(
                ApplicationFormFieldOption.application_form_field_id.in_(field_ids)
            ).delete(synchronize_session=False)
        db.query(ApplicationFormField).filter(
            ApplicationFormField.application_form_id.in_(form_ids)).delete(synchronize_session=False)
    db.query(ApplicationForm).filter_by(branch_id=branch_id).delete(synchronize_session=False)

    sf_ids = [f[0] for f in db.query(ScoringForm.id).filter_by(branch_id=branch_id)]
    if sf_ids:
        db.query(ScoringQuestion).filter(ScoringQuestion.scoring_form_id.in_(sf_ids)
                                         ).delete(synchronize_session=False)
    db.query(ScoringForm).filter_by(branch_id=branch_id).delete(synchronize_session=False)

    applicant_ids = [a[0] for a in db.query(Applicant.id).filter_by(branch_id=branch_id)]
    if applicant_ids:
        db.query(Evaluation).filter(Evaluation.applicant_id.in_(applicant_ids)
                                    ).delete(synchronize_session=False)
    db.query(Applicant).filter_by(branch_id=branch_id).delete(synchronize_session=False)
    db.query(SelectionStage).filter_by(branch_id=branch_id).delete(synchronize_session=False)

    program_ids = [p[0] for p in db.query(Program.id).filter_by(branch_id=branch_id)]
    course_ids = [c[0] for c in db.query(Course.id).filter_by(branch_id=branch_id)]
    biz_ids = [b[0] for b in db.query(Business.id).filter_by(branch_id=branch_id)]

    if course_ids:
        module_ids = [m[0] for m in db.query(Module.id).filter(Module.course_id.in_(course_ids))]
        lesson_ids = [l[0] for l in db.query(Lesson.id).filter(Lesson.module_id.in_(module_ids))] \
            if module_ids else []
        block_ids = [b[0] for b in db.query(ContentBlock.id).filter(
            ContentBlock.lesson_id.in_(lesson_ids))] if lesson_ids else []
        if block_ids:
            db.query(ProgressRecord).filter(ProgressRecord.content_block_id.in_(block_ids)
                                            ).delete(synchronize_session=False)
            db.query(ContentBlock).filter(ContentBlock.id.in_(block_ids)).delete(synchronize_session=False)
        if lesson_ids:
            db.query(Lesson).filter(Lesson.id.in_(lesson_ids)).delete(synchronize_session=False)
        if module_ids:
            db.query(Module).filter(Module.id.in_(module_ids)).delete(synchronize_session=False)
        db.query(Enrollment).filter(Enrollment.course_id.in_(course_ids)).delete(synchronize_session=False)
        db.query(Course).filter_by(branch_id=branch_id).delete(synchronize_session=False)

    if biz_ids:
        db.query(QuestionAnswer).filter(QuestionAnswer.business_id.in_(biz_ids)
                                        ).delete(synchronize_session=False)
        db.query(Mentorship).filter(Mentorship.business_id.in_(biz_ids)).delete(synchronize_session=False)
        db.query(BusinessFounder).filter(BusinessFounder.business_id.in_(biz_ids)
                                         ).delete(synchronize_session=False)
    db.query(Business).filter_by(branch_id=branch_id).delete(synchronize_session=False)

    if program_ids:
        for model in (MentorReviewQuestion, MentorConclusionQuestion):
            db.query(model).filter(model.program_id.in_(program_ids)).delete(synchronize_session=False)
        db.query(Program).filter(Program.id.in_(program_ids)).delete(synchronize_session=False)
    db.query(ProgramType).filter_by(branch_id=branch_id).delete(synchronize_session=False)
    db.query(Document).filter_by(branch_id=branch_id).delete(synchronize_session=False)

    ann_ids = [a[0] for a in db.query(Announcement.id).filter_by(branch_id=branch_id)]
    if ann_ids:
        db.query(AnnouncementReaction).filter(
            AnnouncementReaction.announcement_id.in_(ann_ids)).delete(synchronize_session=False)
    db.query(Announcement).filter_by(branch_id=branch_id).delete(synchronize_session=False)
    db.query(CalendarEvent).filter_by(branch_id=branch_id).delete(synchronize_session=False)

    chat_ids = [c[0] for c in db.query(Chat.id).filter_by(branch_id=branch_id)]
    if chat_ids:
        db.query(ChatMessage).filter(ChatMessage.chat_id.in_(chat_ids)).delete(synchronize_session=False)
        db.query(ChatParticipant).filter(ChatParticipant.chat_id.in_(chat_ids)
                                         ).delete(synchronize_session=False)
        db.query(Chat).filter(Chat.id.in_(chat_ids)).delete(synchronize_session=False)

    db.query(UserRole).filter_by(branch_id=branch_id).delete(synchronize_session=False)
    db.query(Role).filter_by(branch_id=branch_id).delete(synchronize_session=False)
    db.query(Channel).filter_by(branch_id=branch_id).delete(synchronize_session=False)
    db.query(Subindustry).filter_by(branch_id=branch_id).delete(synchronize_session=False)


class BranchPatch(BaseModel):
    name: str | None = None


@router.patch("/branches/{branch_id}/")
def update_branch(branch_id: int, data: BranchPatch, db: Session = Depends(get_db),
                  user=Depends(get_current_user)):
    branch = db.get(Branch, branch_id)
    if not branch:
        raise HTTPException(status_code=404, detail="Not found.")
    _require_org_admin(user, db, branch.organization_id)
    if data.name:
        branch.name = data.name.strip()
    db.commit()
    return {"id": branch.id, "name": branch.name}


@router.delete("/branches/{branch_id}/")
def delete_branch(branch_id: int, cascade: bool = False, db: Session = Depends(get_db),
                  user=Depends(get_current_user)):
    from ..models import Applicant, Business
    branch = db.get(Branch, branch_id)
    if not branch:
        raise HTTPException(status_code=404, detail="Not found.")
    _require_org_admin(user, db, branch.organization_id)
    has_data = (
        db.query(Applicant).filter_by(branch_id=branch_id).count()
        + db.query(Business).filter_by(branch_id=branch_id).count()
        + db.query(UserRole).filter_by(branch_id=branch_id).count()
    )
    if has_data and not cascade:
        raise HTTPException(
            status_code=400,
            detail="Branch still has data. Call again with cascade=true to delete everything in it.")
    _delete_branch_cascade(db, branch_id)
    db.delete(branch)
    db.commit()
    return {"detail": f"Branch {branch.name} deleted."}


@router.delete("/organizations/{org_id}/")
def delete_organization(org_id: int, cascade: bool = False, db: Session = Depends(get_db),
                         user=Depends(get_current_user)):
    org = _require_org_admin(user, db, org_id)
    branches = db.query(Branch).filter_by(organization_id=org_id).all()
    if branches and not cascade:
        raise HTTPException(
            status_code=400,
            detail="Organization still has branches. Call again with cascade=true to delete "
                   "them and all of their data.")
    for b in branches:
        _delete_branch_cascade(db, b.id)
        db.delete(b)
    db.delete(org)
    db.commit()
    return {"detail": f"Organization {org.name} deleted."}


@router.post("/branches/")
def create_branch(data: BranchIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    from ..models import SelectionStage, InvestmentStage
    branch = Branch(organization_id=data.organization_id, name=data.name)
    db.add(branch)
    db.flush()
    stages = ["Track I Onboarding", "Track I Support", "Pitch Stage",
              "Track II Onboarding", "Track II Support"]
    for i, s in enumerate(stages):
        db.add(SelectionStage(branch_id=branch.id, name=s, order=i))
    for i, s in enumerate(["Application", "Evaluation", "Pitching", "Selection", "Approved"]):
        db.add(InvestmentStage(branch_id=branch.id, name=s, order=i))

    # Seed constant roles for the new branch and make the creator its org admin.
    constants = [("Administrator", "branch_admin"), ("Organization Administrator", "organization_admin"),
                 ("Mentor", "mentor"), ("Entrepreneur", "entrepreneur")]
    org_role = None
    for name, code in constants:
        role = Role(branch_id=branch.id, name=name, code_name=code, is_constant=True)
        db.add(role)
        db.flush()
        if code == "organization_admin":
            org_role = role
    if org_role:
        db.add(UserRole(user_id=user.id, role_id=org_role.id, branch_id=branch.id))
    db.commit()
    db.refresh(branch)
    return {"id": branch.id, "name": branch.name}


@router.get("/user-branches/")
def user_branches(user=Depends(get_current_user), db: Session = Depends(get_db)):
    out = []
    for bid in get_user_branch_ids(user, db):
        b = db.get(Branch, bid)
        if not b:
            continue
        org = db.get(Organization, b.organization_id)
        roles = [
            {"id": r.id, "name": r.name, "code_name": r.code_name}
            for r in db.query(Role).join(UserRole, UserRole.role_id == Role.id).filter(
                UserRole.user_id == user.id, UserRole.branch_id == bid).all()
        ]
        out.append({
            "id": bid, "name": b.name,
            "organization": {"id": org.id, "name": org.name} if org else None,
            "roles": roles,
        })
    return out


# ------------------------------------------------------------------ users & roles

@router.get("/v2/users/{branch_id}/")
def users_list(branch_id: int, request: Request, ctx=Depends(require_branch_access())):
    db: Session = ctx["db"]
    page, size = parse_page(request)
    q = db.query(User).join(UserRole, UserRole.user_id == User.id).filter(UserRole.branch_id == branch_id)
    search = request.query_params.get("search")
    if search:
        like = f"%{search}%"
        q = q.filter((User.first_name.ilike(like)) | (User.last_name.ilike(like)) | (User.email.ilike(like)))
    role = request.query_params.get("role")
    if role:
        q = q.join(Role, Role.id == UserRole.role_id).filter(Role.code_name == role)
    status = request.query_params.get("status")
    if status:
        q = q.join(UserStatus, UserStatus.id == User.status_id).filter(UserStatus.code_name == status)
    ordering = request.query_params.get("ordering", "first_name")
    col = {
        "first_name": User.first_name, "-first_name": User.first_name.desc(),
        "last_name": User.last_name, "email": User.email,
    }.get(ordering, User.first_name)
    q = q.distinct().order_by(col)
    return paginate(q, page, size, lambda u: user_row(u, db, branch_id))


@router.get("/users/{branch_id}/mentors/")
def mentors_list(branch_id: int, ctx=Depends(require_branch_access())):
    db: Session = ctx["db"]
    rows = db.query(User).join(UserRole, UserRole.user_id == User.id).join(
        Role, Role.id == UserRole.role_id).filter(
        UserRole.branch_id == branch_id, Role.code_name.in_(["mentor", "branch_admin"])).distinct().all()
    return [{"id": u.id, "name": f"{u.first_name} {u.last_name}".strip(), "email": u.email} for u in rows]


@router.get("/users/{branch_id}/{user_id}/")
def user_detail(branch_id: int, user_id: int, ctx=Depends(require_branch_access())):
    db: Session = ctx["db"]
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="Not found.")
    return user_row(u, db, branch_id)


class InviteUserIn(BaseModel):
    email: str
    first_name: str = ""
    last_name: str = ""
    position: str = ""
    company: str = ""
    role_id: int | None = None
    role_ids: list[int] | None = None
    password: str = ""


@router.post("/users/{branch_id}/invite/")
def invite_user(branch_id: int, data: InviteUserIn, ctx=Depends(require_perm("users.manage"))):
    db: Session = ctx["db"]
    email = data.email.strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required.")
    user = db.query(User).filter(User.email == email).first()
    from ..security import hash_password
    if not user:
        user = User(
            email=email,
            password_hash=hash_password(data.password or "Welcome123!"),
            first_name=data.first_name,
            last_name=data.last_name,
            position=data.position,
            company=data.company,
        )
        invited = db.query(UserStatus).filter(UserStatus.code_name == "invited").first()
        user.status_id = invited.id if invited else None
        db.add(user)
        db.flush()
    else:
        if data.first_name:
            user.first_name = data.first_name
        if data.last_name:
            user.last_name = data.last_name
        if data.position:
            user.position = data.position
        if data.company:
            user.company = data.company
        if data.password:
            user.password_hash = hash_password(data.password)

    target_role_ids = []
    if data.role_ids:
        target_role_ids = [int(rid) for rid in data.role_ids if rid]
    elif data.role_id:
        target_role_ids = [int(data.role_id)]

    for rid in target_role_ids:
        exists = db.query(UserRole).filter_by(user_id=user.id, branch_id=branch_id, role_id=rid).first()
        if not exists:
            db.add(UserRole(user_id=user.id, role_id=rid, branch_id=branch_id))

    db.commit()
    return user_row(user, db, branch_id)


@router.patch("/users/{branch_id}/{user_id}/")
def update_user(branch_id: int, user_id: int, data: dict, ctx=Depends(require_perm("users.manage"))):
    db: Session = ctx["db"]
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="User not found.")

    for f in ("first_name", "last_name", "position", "company"):
        if f in data and data[f] is not None:
            setattr(u, f, str(data[f]).strip())

    if "email" in data and data["email"]:
        new_email = str(data["email"]).strip().lower()
        if new_email != u.email:
            existing = db.query(User).filter(User.email == new_email).first()
            if existing and existing.id != u.id:
                raise HTTPException(status_code=400, detail="A user with this email already exists.")
            u.email = new_email

    if "password" in data and data["password"]:
        pw = str(data["password"]).strip()
        if len(pw) < 6:
            raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")
        from ..security import hash_password
        u.password_hash = hash_password(pw)

    if "status" in data and data["status"] is not None:
        status_val = data["status"]
        if isinstance(status_val, int) or (isinstance(status_val, str) and str(status_val).isdigit()):
            st = db.get(UserStatus, int(status_val))
        else:
            code = str(status_val).lower().strip()
            st = db.query(UserStatus).filter(
                (UserStatus.code_name == code) | (UserStatus.name.ilike(code))
            ).first()
            if not st:
                st = UserStatus(name=code.capitalize(), code_name=code)
                db.add(st)
                db.flush()
        if st:
            u.status_id = st.id
    elif "status_id" in data and data["status_id"] is not None:
        st = db.get(UserStatus, int(data["status_id"]))
        if st:
            u.status_id = st.id

    # Handle roles assignment
    if "role_ids" in data and data["role_ids"] is not None:
        new_role_ids = [int(rid) for rid in data["role_ids"] if rid]
        valid_roles = db.query(Role).filter(
            Role.id.in_(new_role_ids or [0]),
            (Role.branch_id == branch_id) | (Role.branch_id.is_(None))
        ).all()
        valid_role_ids = {r.id for r in valid_roles}

        db.query(UserRole).filter(
            UserRole.user_id == user_id,
            UserRole.branch_id == branch_id
        ).delete(synchronize_session=False)

        for rid in valid_role_ids:
            db.add(UserRole(user_id=user_id, role_id=rid, branch_id=branch_id))

    elif "role_id" in data and data["role_id"] is not None:
        rid = int(data["role_id"])
        db.query(UserRole).filter(
            UserRole.user_id == user_id,
            UserRole.branch_id == branch_id
        ).delete(synchronize_session=False)
        db.add(UserRole(user_id=user_id, role_id=rid, branch_id=branch_id))

    db.commit()
    db.refresh(u)
    return user_row(u, db, branch_id)


@router.delete("/users/{branch_id}/{user_id}/")
def delete_user_from_branch(branch_id: int, user_id: int, ctx=Depends(require_perm("users.manage"))):
    db: Session = ctx["db"]
    current_user = ctx["user"]
    if current_user.id == user_id:
        raise HTTPException(
            status_code=400,
            detail="You cannot remove or deactivate your own account.",
        )
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="User not found.")

    db.query(UserRole).filter(UserRole.user_id == user_id, UserRole.branch_id == branch_id).delete(synchronize_session=False)

    other_branches = db.query(UserRole).filter(UserRole.user_id == user_id).count()
    if other_branches == 0:
        inactive = db.query(UserStatus).filter(UserStatus.code_name == "inactive").first()
        if inactive:
            u.status_id = inactive.id

    db.commit()
    return {"detail": f"User {u.first_name} {u.last_name} removed from branch successfully."}


@router.get("/roles/{branch_id}/")
def roles_list(branch_id: int, ctx=Depends(require_branch_access())):
    db: Session = ctx["db"]
    rows = db.query(Role).filter((Role.branch_id == branch_id) | (Role.branch_id.is_(None))).all()
    return [{
        "id": r.id, "name": r.name, "code_name": r.code_name, "is_constant": bool(r.is_constant),
        "permissions": r.permissions or [],
        "users_count": db.query(UserRole).filter(UserRole.role_id == r.id).count(),
    } for r in rows]


class RoleIn(BaseModel):
    name: str
    code_name: str
    permissions: list[str] = []


@router.post("/roles/{branch_id}/")
def create_role(branch_id: int, data: RoleIn, ctx=Depends(require_perm("users.manage"))):
    db: Session = ctx["db"]
    if db.query(Role).filter_by(branch_id=branch_id, code_name=data.code_name).first():
        raise HTTPException(status_code=400, detail="A role with this code already exists.")
    role = Role(branch_id=branch_id, name=data.name, code_name=data.code_name,
                is_constant=False, permissions=data.permissions)
    db.add(role)
    db.commit()
    db.refresh(role)
    return {"id": role.id, "name": role.name, "code_name": role.code_name,
            "is_constant": False, "permissions": role.permissions}


@router.get("/user-roles/{branch_id}/")
def user_roles(branch_id: int, ctx=Depends(require_branch_access())):
    db: Session = ctx["db"]
    rows = db.query(UserRole, User, Role).join(User, User.id == UserRole.user_id).join(
        Role, Role.id == UserRole.role_id).filter(UserRole.branch_id == branch_id).all()
    return [{
        "id": ur.id, "user_id": u.id, "user_name": f"{u.first_name} {u.last_name}".strip(),
        "role": {"id": r.id, "name": r.name, "code_name": r.code_name},
        "branch_id": ur.branch_id,
    } for ur, u, r in rows]


@router.get("/user-statuses/")
def user_statuses(db: Session = Depends(get_db)):
    defaults = [
        ("Active", "active"),
        ("Invited", "invited"),
        ("Suspended", "suspended"),
        ("Inactive", "inactive"),
    ]
    for name, code in defaults:
        if not db.query(UserStatus).filter(UserStatus.code_name == code).first():
            db.add(UserStatus(name=name, code_name=code))
            db.commit()
    return [serialize_ref(s) for s in db.query(UserStatus).all()]


# ------------------------------------------------------------------ System Maintenance & Data Reset

class ResetDataIn(BaseModel):
    mode: str = "wipe"  # "wipe" or "reseed"
    confirmation: str = ""


def _require_admin_role(user, db: Session, branch_id: int):
    all_role_ids = [r[0] for r in db.query(UserRole.role_id).filter_by(user_id=user.id).all()]
    codes = {r[0] for r in db.query(Role.code_name).filter(Role.id.in_(all_role_ids or [0]))}
    if not codes & {"branch_admin", "organization_admin", "*"}:
        raise HTTPException(status_code=403, detail="Only administrators can reset system data.")


@router.get("/system/entrepreneur-data-stats/{branch_id}/")
def get_entrepreneur_data_stats(branch_id: int, ctx=Depends(require_branch_access())):
    db: Session = ctx["db"]
    _require_admin_role(ctx["user"], db, branch_id)

    from ..models import (
        Applicant, Business, DisbursementBatch, InvestmentCase, Role, UserRole,
    )
    biz_count = db.query(Business).filter(Business.branch_id == branch_id).count()
    app_count = db.query(Applicant).filter(Applicant.branch_id == branch_id).count()
    batch_count = db.query(DisbursementBatch).filter(DisbursementBatch.branch_id == branch_id).count()
    case_count = db.query(InvestmentCase).filter(InvestmentCase.branch_id == branch_id).count()

    role_e = db.query(Role).filter((Role.branch_id == branch_id) | (Role.branch_id.is_(None))).filter(Role.code_name == "entrepreneur").all()
    role_e_ids = [r.id for r in role_e]
    entrepreneurs_count = db.query(UserRole).filter(UserRole.branch_id == branch_id, UserRole.role_id.in_(role_e_ids)).count() if role_e_ids else 0

    return {
        "branch_id": branch_id,
        "applicants_count": app_count,
        "businesses_count": biz_count,
        "disbursements_count": batch_count,
        "investment_cases_count": case_count,
        "entrepreneurs_count": entrepreneurs_count,
    }


@router.post("/system/reset-entrepreneur-data/{branch_id}/")
def reset_entrepreneur_data_endpoint(branch_id: int, data: ResetDataIn, ctx=Depends(require_branch_access())):
    db: Session = ctx["db"]
    _require_admin_role(ctx["user"], db, branch_id)

    if data.confirmation.strip().upper() != "RESET":
        raise HTTPException(status_code=400, detail="Please type RESET to confirm data deletion.")

    from ..models import (
        Applicant, Business, BusinessFounder, CommitteeDecision,
        DisbursementBatch, DisbursementItem, Document, Enrollment, Evaluation,
        FinanceTimelineEntry, InvestmentCase, Mentorship, PaymentScheduleEntry,
        ProgressRecord, QuestionAnswer, Role, User, UserRole,
    )

    # 1. Disbursements
    batch_ids = [b[0] for b in db.query(DisbursementBatch.id).filter(DisbursementBatch.branch_id == branch_id).all()]
    if batch_ids:
        db.query(DisbursementItem).filter(DisbursementItem.batch_id.in_(batch_ids)).delete(synchronize_session=False)
    db.query(DisbursementBatch).filter(DisbursementBatch.branch_id == branch_id).delete(synchronize_session=False)

    # 2. Investment cases & decisions
    case_ids = [c[0] for c in db.query(InvestmentCase.id).filter(InvestmentCase.branch_id == branch_id).all()]
    if case_ids:
        db.query(CommitteeDecision).filter(CommitteeDecision.case_id.in_(case_ids)).delete(synchronize_session=False)
        db.query(PaymentScheduleEntry).filter(PaymentScheduleEntry.case_id.in_(case_ids)).delete(synchronize_session=False)
        db.query(FinanceTimelineEntry).filter(FinanceTimelineEntry.case_id.in_(case_ids)).delete(synchronize_session=False)
        db.query(InvestmentCase).filter(InvestmentCase.branch_id == branch_id).delete(synchronize_session=False)

    # 3. Businesses, founders, mentorships, reviews, docs
    biz_ids = [b[0] for b in db.query(Business.id).filter(Business.branch_id == branch_id).all()]
    if biz_ids:
        db.query(BusinessFounder).filter(BusinessFounder.business_id.in_(biz_ids)).delete(synchronize_session=False)
        db.query(Mentorship).filter(Mentorship.business_id.in_(biz_ids)).delete(synchronize_session=False)
        db.query(QuestionAnswer).filter(QuestionAnswer.business_id.in_(biz_ids)).delete(synchronize_session=False)
        db.query(Document).filter(Document.business_id.in_(biz_ids)).delete(synchronize_session=False)
    db.query(Business).filter(Business.branch_id == branch_id).delete(synchronize_session=False)

    # 4. Applicants, evaluations
    app_ids = [a[0] for a in db.query(Applicant.id).filter(Applicant.branch_id == branch_id).all()]
    if app_ids:
        db.query(Evaluation).filter(Evaluation.applicant_id.in_(app_ids)).delete(synchronize_session=False)
        db.query(Applicant).filter(Applicant.branch_id == branch_id).delete(synchronize_session=False)

    # 5. Course enrollments & progress for entrepreneurs in this branch
    role_e = db.query(Role).filter((Role.branch_id == branch_id) | (Role.branch_id.is_(None))).filter(Role.code_name == "entrepreneur").all()
    role_e_ids = [r.id for r in role_e]
    if role_e_ids:
        entrepreneur_user_ids = [
            ur.user_id for ur in db.query(UserRole).filter(
                UserRole.branch_id == branch_id,
                UserRole.role_id.in_(role_e_ids)
            ).all()
        ]
        if entrepreneur_user_ids:
            staff_role_ids = [
                r.id for r in db.query(Role.id).filter(
                    ~Role.code_name.in_(["entrepreneur"])
                ).all()
            ]
            staff_user_ids = set(
                ur.user_id for ur in db.query(UserRole.user_id).filter(
                    UserRole.user_id.in_(entrepreneur_user_ids),
                    UserRole.role_id.in_(staff_role_ids)
                ).all()
            )
            users_to_delete = [uid for uid in entrepreneur_user_ids if uid not in staff_user_ids]
            if users_to_delete:
                db.query(ProgressRecord).filter(ProgressRecord.user_id.in_(users_to_delete)).delete(synchronize_session=False)
                db.query(Enrollment).filter(Enrollment.user_id.in_(users_to_delete)).delete(synchronize_session=False)
                db.query(UserRole).filter(UserRole.user_id.in_(users_to_delete)).delete(synchronize_session=False)
                db.query(User).filter(User.id.in_(users_to_delete)).delete(synchronize_session=False)

    db.commit()

    reseeded = False
    if data.mode == "reseed":
        _reseed_entrepreneur_data_for_branch(db, branch_id)
        reseeded = True

    return {
        "success": True,
        "mode": data.mode,
        "reseeded": reseeded,
        "message": "Entrepreneur data has been completely reset" + (" and re-seeded with demo data." if reseeded else "."),
    }


COHORT3_RECONCILED = [
    (1, 'Marines', 'Abdelrahman Mohamamed Alshamaileh', [250, 250, 250, 250, 250, 0, 0], [1000, 0, 0]),
    (2, 'ShortlistOn', 'Adel Fayez Adel Al Eid', [250, 250, 250, 250, 250, 0, 250], [1000, 0, 0]),
    (3, 'audiomatic.io', 'Ahmad Abdul Majed Mohammad Hammoude', [250, 250, 0, 0, 750, 0, 0], [0, 0, 1000]),
    (4, 'Azrar.ai', 'Ahmad Ghassan Ahmad Jaber', [250, 0, 500, 250, 0, 0, 0], [1000, 0, 0]),
    (5, 'Learnfy.Ai', 'Ahmad Naser Hasan Alabed Alhadi', [250, 0, 500, 250, 250, 0, 250], [1000, 0, 0]),
    (6, 'Trevx', 'Ahmad Rasmi Ahmad Almubiden', [250, 250, 250, 250, 250, 0, 250], [1000, 0, 0]),
    (7, 'تطبيق اي فوترة', 'Ahmad Zaki Mohammad Qandeel', [250, 250, 250, 250, 250, 0, 250], [1000, 0, 0]),
    (8, 'the act cast', 'Aseel Ihssan Mahmoud Yaseen', [250, 250, 250, 250, 250, 0, 250], [1000, 0, 0]),
    (9, 'حواس', 'Aseel Said Mohammad Shaqra', [250, 250, 250, 250, 250, 0, 250], [1000, 0, 0]),
    (10, 'MA3', 'Aws Karem Mohamoud Barghouthi', [250, 250, 0, 500, 250, 0, 250], [0, 1000, 0]),
    (11, 'Banofi Pack', 'Aya Mohammad Hashem Salameh', [250, 250, 250, 250, 250, 0, 250], [1000, 0, 0]),
    (12, 'NOA | نواة', 'Ayah Abdallah Waleed Alwazani', [250, 250, 0, 0, 0, 0, 0], [0, 0, 0]),
    (13, 'LaserLink', 'Bashar Khaled Mohammad Alshami', [250, 250, 250, 250, 0, 250, 250], [1000, 0, 0]),
    (14, 'Manzel', 'Hadeel Mahmoud Mohammad Balasmeh', [250, 250, 250, 250, 250, 0, 250], [1000, 0, 0]),
    (15, 'ERP System "EXP"', 'Hamza Mahmmoud Abed Shaheen', [250, 250, 250, 250, 250, 0, 250], [1000, 0, 0]),
    (16, 'Dragon Organic Solutions', 'Hanadi Husain Ibrahim Al Hyari', [250, 250, 250, 250, 250, 0, 250], [1000, 0, 0]),
    (17, 'مزرعتي mazrite', 'Laith Khaled S.Mustafa', [250, 250, 250, 250, 250, 0, 250], [1000, 0, 0]),
    (18, 'Hangar', 'Laith Sa\'Id Mohammad Obeidat', [250, 250, 250, 250, 250, 0, 250], [1000, 0, 0]),
    (19, 'Wujood', 'Leen Mohamamd Abdelkareem Alhassan', [250, 250, 250, 250, 250, 0, 0], [1000, 0, 0]),
    (20, 'Headache Cap', 'Luay Peter Shafiq Petro', [250, 250, 0, 500, 250, 0, 0], [0, 1000, 0]),
    (21, 'BarqBoxes', 'Moayad Mahmoud Abed Alnajdawi', [250, 250, 250, 250, 250, 0, 250], [1000, 0, 0]),
    (22, 'TIKRAR', 'Mohammad Bassam Ali Bazbaz', [250, 0, 500, 250, 250, 0, 250], [1000, 0, 0]),
    (23, 'Green Clean Solar Energy', 'Mohammad Ibrahim Ahmad Bzour', [250, 250, 250, 250, 250, 0, 250], [1000, 0, 0]),
    (24, 'Aman', 'Mohammad Issam Musa Arabieh', [250, 250, 250, 0, 0, 0, 0], [1000, 0, 0]),
    (25, 'Avenzoar', 'Mohammad Jammal Adel Alkhatib', [250, 250, 250, 250, 250, 0, 250], [1000, 0, 0]),
    (26, 'Basket of life', 'Mohammad Khader Mohammad Muhaisen', [250, 250, 250, 250, 250, 0, 0], [1000, 0, 0]),
    (27, 'GGEZ1', 'Mu\'Taz Ma\'En Rafiq Majdoub', [250, 250, 250, 250, 250, 0, 250], [1000, 0, 0]),
    (28, 'TourSplit', 'Nasser Atef Abdo Farag Abu Alsa\'Ad', [250, 250, 250, 250, 250, 0, 250], [1000, 0, 0]),
    (29, 'كانف - canve', 'Nihad Abdalraheem Almekdad', [250, 250, 250, 250, 250, 0, 250], [1000, 0, 0]),
    (30, 'WeightTRON', 'Omar Khader Qasim Irshaidat', [250, 0, 500, 250, 0, 250, 250], [1000, 0, 0]),
    (31, 'iPlant', 'Omar Marwan Husni Bawab', [250, 250, 250, 250, 250, 0, 250], [1000, 0, 0]),
    (32, 'TrendPin', 'Omar Moh\'D Mazen Abed Alfatth Abura', [250, 250, 250, 250, 250, 0, 250], [1000, 0, 0]),
    (33, 'ProBreeder', 'Raghad Ahmad Mustafa Al-Nobani', [250, 250, 250, 250, 250, 0, 250], [1000, 0, 0]),
    (34, 'Ngoot', 'Raghad Ali Moharib Abu Wadi', [250, 250, 250, 250, 250, 0, 250], [1000, 0, 0]),
    (35, 'Greener - GWS 360', 'Saleh Iyad Saleh Abuelezz', [250, 250, 0, 500, 250, 0, 0], [0, 1000, 0]),
    (36, 'Oasta', 'Samaa Taha Theeb Abdallah', [250, 250, 250, 250, 250, 0, 0], [1000, 0, 0]),
    (37, 'V2X Ventures', 'Samia Ghassan Husam Sharawi', [250, 250, 250, 250, 0, 0, 250], [1000, 0, 0]),
    (38, 'House of Shorouq', 'Shrouq Mohammad Mahmoud Al-Mazrawi', [250, 250, 250, 250, 250, 0, 250], [1000, 0, 0]),
    (39, 'بنات العيله للحياكه', 'Suad Yahia Ahmad Battikha', [250, 250, 250, 250, 250, 0, 250], [1000, 0, 0]),
    (40, 'SpineVision Diagnostics', 'Tasneem Naser Mustafa Alhousani', [250, 250, 250, 250, 250, 0, 250], [1000, 0, 0]),
]


def _reseed_entrepreneur_data_for_branch(db: Session, branch_id: int):
    """Populates realistic applicant, business, and disbursement demo records for a branch."""
    import random
    from datetime import date, datetime, timedelta
    from ..models import (
        Applicant, ApplicantStatus, Business, BusinessFounder, BusinessIndustry,
        BusinessType, Channel, Country, DisbursementBatch, DisbursementItem,
        District, Gender, InvestmentCase, InvestmentRound, InvestmentStage,
        InvestmentStatus, Mentorship, Program, Province, SelectionStage, User,
    )

    programs = db.query(Program).filter(Program.branch_id == branch_id).all()
    if not programs:
        return

    p1 = programs[0]

    stages = db.query(SelectionStage).filter(SelectionStage.branch_id == branch_id).all()
    channel = db.query(Channel).filter(Channel.branch_id == branch_id).first()
    genders = db.query(Gender).all()
    countries = db.query(Country).all()
    provinces = db.query(Province).all()
    districts = db.query(District).all()
    industries = db.query(BusinessIndustry).all()
    types = db.query(BusinessType).all()
    statuses = db.query(ApplicantStatus).all()
    admin_user = db.query(User).filter(User.email.like("%admin%")).first()

    # 1. Create 40 exact Cohort 3 Track I applicants & businesses
    applicants = []
    cohort3_businesses = []

    for idx, sname, fname, _, _ in COHORT3_RECONCILED:
        parts = fname.split(' ', 1)
        fn = parts[0]
        ln = parts[1] if len(parts) > 1 else ''
        gender = random.choice(genders) if genders else None
        country = random.choice(countries) if countries else None
        province = random.choice(provinces) if provinces else None
        district = random.choice(districts) if districts else None
        industry = random.choice(industries) if industries else None
        stage = stages[1] if len(stages) > 1 else (stages[0] if stages else None)
        status = statuses[0] if statuses else None

        ap = Applicant(
            branch_id=branch_id,
            program_id=p1.id,
            selection_stage_id=stage.id if stage else None,
            status_id=status.id if status else None,
            email=f"{fn.lower()}.{ln.lower().replace(' ', '_')}@startup.jo",
            first_name=fn,
            last_name=ln,
            business_name=sname,
            country_id=country.id if country else None,
            province_id=province.id if province else None,
            district_id=district.id if district else None,
            industry_id=industry.id if industry else None,
            gender_id=gender.id if gender else None,
            channel_id=channel.id if channel else None,
            age=random.randint(22, 50),
            average_score=round(random.uniform(70, 95), 1),
            registered=True,
            application_date=datetime(2025, 8, 1),
        )
        applicants.append(ap)
        db.add(ap)
        db.flush()

        b = Business(
            branch_id=branch_id,
            program_id=p1.id,
            applicant_id=ap.id,
            name=sname,
            type_id=random.choice(types).id if types else None,
            industry_id=industry.id if industry else None,
            graduation_status="Not graduated",
            course_progress=round(random.uniform(40, 100), 1),
            course_score=round(random.uniform(60, 98), 1),
            average_evaluator_score=ap.average_score,
            created_at=datetime(2025, 8, 1),
        )
        b.founders.append(BusinessFounder(
            first_name=fn, last_name=ln, email=ap.email,
            gender_id=ap.gender_id, age=ap.age, position="Founder & CEO"
        ))
        db.add(b)
        cohort3_businesses.append(b)

    db.commit()

    # 2. Create 7 Monthly Allowance Batches (Reconciled)
    MONTH_DATES = [
        ('Aug-25', date(2025, 8, 31), 'Monthly Stipend — August 2025'),
        ('Sep-25', date(2025, 9, 30), 'Monthly Stipend — September 2025'),
        ('Oct-25', date(2025, 10, 31), 'Monthly Stipend — October 2025'),
        ('Nov-25', date(2025, 11, 30), 'Monthly Stipend — November 2025'),
        ('Dec-25', date(2025, 12, 31), 'Monthly Stipend — December 2025'),
        ('Jan-26', date(2026, 1, 31), 'Monthly Stipend — January 2026'),
        ('Feb-26', date(2026, 2, 28), 'Monthly Stipend — February 2026'),
    ]

    for m_idx, (m_label, m_date, m_title) in enumerate(MONTH_DATES):
        batch = DisbursementBatch(
            branch_id=branch_id,
            program_id=p1.id,
            title=f'Cohort 3 Track I: {m_title}',
            payment_date=m_date,
            currency='EUR',
            base_amount=250.0,
            notes=f'Official monthly allowance payment for {m_label} (Reconciled).',
            status='processed',
            confirmed_by_id=admin_user.id if admin_user else None,
            confirmed_at=datetime(m_date.year, m_date.month, m_date.day, 12, 0),
        )
        db.add(batch)
        db.flush()

        b_total = 0.0
        for r_idx, b in enumerate(cohort3_businesses):
            amt = float(COHORT3_RECONCILED[r_idx][3][m_idx])
            pct = int(amt / 250.0 * 100)
            note = 'Includes deferred previous month payment' if amt == 500 else 'Includes 3-month catch-up payment' if amt == 750 else 'Deferred' if amt == 0 else ''
            db.add(DisbursementItem(batch_id=batch.id, business_id=b.id, percentage=pct, amount=amt, notes=note))
            b_total += amt
        batch.total_amount = b_total
        db.commit()

    # 4. Create 3 Prototype Voucher Batches (Reconciled)
    PROTO_MONTHS = [
        (0, 'Oct-25', date(2025, 10, 31), 'Prototype Voucher — October 2025 Batch'),
        (1, 'Nov-25', date(2025, 11, 30), 'Prototype Voucher — November 2025 Batch'),
        (2, 'Dec-25', date(2025, 12, 31), 'Prototype Voucher — December 2025 Batch'),
    ]

    for p_idx, p_label, p_date, p_title in PROTO_MONTHS:
        batch = DisbursementBatch(
            branch_id=branch_id,
            program_id=p1.id,
            title=f'Cohort 3 Track I: {p_title}',
            payment_date=p_date,
            currency='EUR',
            base_amount=1000.0,
            notes=f'One-off prototype voucher milestone disbursement for {p_label} (Reconciled).',
            status='processed',
            confirmed_by_id=admin_user.id if admin_user else None,
            confirmed_at=datetime(p_date.year, p_date.month, p_date.day, 12, 0),
        )
        db.add(batch)
        db.flush()

        p_total = 0.0
        for r_idx, b in enumerate(cohort3_businesses):
            amt = float(COHORT3_RECONCILED[r_idx][4][p_idx])
            pct = 100 if amt == 1000 else 0
            note = 'Prototype milestone approved' if amt == 1000 else 'Prototype milestone not in this batch'
            db.add(DisbursementItem(batch_id=batch.id, business_id=b.id, percentage=pct, amount=amt, notes=note))
            p_total += amt
        batch.total_amount = p_total
        db.commit()

    db.commit()

