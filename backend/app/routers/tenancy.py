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
    role_id: int
    password: str = ""


@router.post("/users/{branch_id}/invite/")
def invite_user(branch_id: int, data: InviteUserIn, ctx=Depends(require_perm("users.manage"))):
    db: Session = ctx["db"]
    email = data.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user:
        from ..security import hash_password
        user = User(
            email=email,
            password_hash=hash_password(data.password or "Welcome123!"),
            first_name=data.first_name, last_name=data.last_name, position=data.position,
        )
        invited = db.query(UserStatus).filter(UserStatus.code_name == "invited").first()
        user.status_id = invited.id if invited else None
        db.add(user)
        db.flush()
    exists = db.query(UserRole).filter_by(user_id=user.id, branch_id=branch_id, role_id=data.role_id).first()
    if not exists:
        db.add(UserRole(user_id=user.id, role_id=data.role_id, branch_id=branch_id))
    db.commit()
    return {"id": user.id, "detail": "User added to branch."}


@router.patch("/users/{branch_id}/{user_id}/")
def update_user(branch_id: int, user_id: int, data: dict, ctx=Depends(require_perm("users.manage"))):
    db: Session = ctx["db"]
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="Not found.")
    for f in ("first_name", "last_name", "position", "company"):
        if f in data:
            setattr(u, f, data[f])
    if "status" in data:
        st = db.query(UserStatus).filter(UserStatus.code_name == data["status"]).first()
        if st:
            u.status_id = st.id
    if "role_id" in data and data["role_id"]:
        link = db.query(UserRole).filter_by(user_id=user_id, branch_id=branch_id).first()
        if link:
            link.role_id = data["role_id"]
    db.commit()
    return user_row(u, db, branch_id)


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
    return [serialize_ref(s) for s in db.query(UserStatus).all()]
