from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_branch_access, require_perm
from ..models import (
    Announcement, AnnouncementReaction, CalendarEvent, Chat, ChatMessage, ChatParticipant,
    Notification,
)
from ..utils import paginate, parse_page


def announcement_ser(a: Announcement) -> dict:
    return {
        "id": a.id, "branch": a.branch_id, "program_id": a.program_id,
        "title": a.title, "body": a.body,
        "published_at": str(a.published_at or ""),
        "reactions_count": a.reactions_count,
        "status_id": a.status_id,
    }


router = APIRouter(tags=["collaboration"])


# ------------------------------------------------------------------ announcements

@router.get("/announcements/{branch_id}/")
def announcements_list(branch_id: int, request: Request, ctx=Depends(require_perm("announcements.view"))):
    db: Session = ctx["db"]
    page, size = parse_page(request)
    q = db.query(Announcement).filter(Announcement.branch_id == branch_id)
    if v := request.query_params.get("status"):
        q = q.filter(Announcement.status_id == int(v))
    if v := request.query_params.get("program"):
        q = q.filter((Announcement.program_id == int(v)) | (Announcement.program_id.is_(None)))
    q = q.order_by(Announcement.published_at.desc())
    user_id = ctx["user"].id
    reacted = {r[0] for r in db.query(AnnouncementReaction.announcement_id).filter_by(user_id=user_id)}

    def ser(a):
        data = announcement_ser(a)
        data["reacted"] = a.id in reacted
        return data
    return paginate(q, page, size, ser)


class AnnouncementIn(BaseModel):
    title: str
    body: str = ""
    program_id: int | None = None
    status: str | None = None   # draft | published


@router.post("/announcements/{branch_id}/")
def create_announcement(branch_id: int, data: AnnouncementIn,
                        ctx=Depends(require_perm("announcements.edit"))):
    from ..models import AnnouncementStatus, Notification, User, UserRole
    db: Session = ctx["db"]
    status = db.query(AnnouncementStatus).filter(
        AnnouncementStatus.code_name == (data.status or "draft")).first()
    a = Announcement(
        branch_id=branch_id, program_id=data.program_id, title=data.title, body=data.body,
        status_id=status.id if status else None, published_at=datetime.utcnow(),
    )
    db.add(a)
    db.flush()
    if status and status.code_name == "published":
        for (uid,) in db.query(UserRole.user_id).filter(UserRole.branch_id == branch_id).distinct():
            db.add(Notification(
                user_id=uid, type="announcement",
                payload={"message": f"New announcement: {data.title}", "announcement_id": a.id}))
    db.commit()
    db.refresh(a)
    return announcement_ser(a)


@router.patch("/announcements/{branch_id}/{announcement_id}/")
def update_announcement(branch_id: int, announcement_id: int, data: dict,
                        ctx=Depends(require_perm("announcements.edit"))):
    db: Session = ctx["db"]
    a = db.get(Announcement, announcement_id)
    if not a or a.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Not found.")
    if "title" in data:
        a.title = data["title"]
    if "body" in data:
        a.body = data["body"]
    if "status" in data:
        from ..models import AnnouncementStatus
        st = db.query(AnnouncementStatus).filter_by(code_name=data["status"]).first()
        if st:
            a.status_id = st.id
    db.commit()
    return announcement_ser(a)


@router.post("/announcements/{branch_id}/{announcement_id}/react/")
def react_announcement(branch_id: int, announcement_id: int, ctx=Depends(require_perm("announcements.view"))):
    """Lightweight social acknowledgement (spec §6.2)."""
    db: Session = ctx["db"]
    a = db.get(Announcement, announcement_id)
    if not a or a.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Not found.")
    existing = db.query(AnnouncementReaction).filter_by(
        announcement_id=a.id, user_id=ctx["user"].id).first()
    if existing:
        db.delete(existing)
        a.reactions_count = max(0, a.reactions_count - 1)
        action = "removed"
    else:
        db.add(AnnouncementReaction(announcement_id=a.id, user_id=ctx["user"].id))
        a.reactions_count += 1
        action = "added"
    db.commit()
    return {"action": action, "reactions_count": a.reactions_count}


# ------------------------------------------------------------------ calendar

@router.get("/calendar-events/{branch_id}/")
def calendar_events(branch_id: int, request: Request, ctx=Depends(require_perm("calendar.view"))):
    db: Session = ctx["db"]
    t = request.query_params.get("type", "all")
    uid = ctx["user"].id
    q = db.query(CalendarEvent).filter(CalendarEvent.branch_id == branch_id)
    if t in ("public", "private"):
        q = q.filter(CalendarEvent.visibility == t)
    rows = q.order_by(CalendarEvent.start).all()
    # private events are only visible to their creator
    return [{
        "id": e.id, "title": e.title, "description": e.description,
        "start": str(e.start or ""), "end": str(e.end or ""),
        "visibility": e.visibility, "created_by_id": e.created_by_id,
        "mine": e.created_by_id == uid,
    } for e in rows if e.visibility == "public" or e.created_by_id == uid]


class EventIn(BaseModel):
    title: str
    description: str = ""
    start: str
    end: str | None = None
    visibility: str = "public"


@router.post("/calendar-events/{branch_id}/")
def create_event(branch_id: int, data: EventIn, ctx=Depends(require_perm("calendar.view"))):
    db: Session = ctx["db"]
    try:
        start = datetime.fromisoformat(data.start.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid start datetime.")
    end = None
    if data.end:
        try:
            end = datetime.fromisoformat(data.end.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            pass
    e = CalendarEvent(
        branch_id=branch_id, title=data.title, description=data.description,
        start=start, end=end, visibility=data.visibility if data.visibility in ("public", "private") else "public",
        created_by_id=ctx["user"].id,
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return {"id": e.id, "title": e.title}


@router.delete("/calendar-events/{branch_id}/{event_id}/")
def delete_event(branch_id: int, event_id: int, ctx=Depends(require_branch_access())):
    db: Session = ctx["db"]
    e = db.get(CalendarEvent, event_id)
    if not e or e.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Not found.")
    if e.created_by_id != ctx["user"].id and "users.manage" not in ctx["roles"]:
        raise HTTPException(status_code=403, detail="You do not have permission to perform this action.")
    db.delete(e)
    db.commit()
    return {"detail": "Deleted"}


# ------------------------------------------------------------------ chat

@router.post("/user-chats/")
def create_chat(data: dict, ctx=Depends(require_perm("chat.use"))):
    db: Session = ctx["db"]
    user = ctx["user"]
    branch_id = data.get("branch_id") or user and None
    if not branch_id:
        raise HTTPException(status_code=400, detail="branch_id is required.")
    participant_ids = list({int(i) for i in data.get("participants", [])} | {user.id})
    chat = Chat(branch_id=int(branch_id),
                program_id=data.get("program_id"),
                is_group=len(participant_ids) > 2,
                title=data.get("title") or "")
    db.add(chat)
    db.flush()
    for pid in participant_ids:
        db.add(ChatParticipant(chat_id=chat.id, user_id=pid))
    db.commit()
    db.refresh(chat)
    return {"id": chat.id, "is_group": chat.is_group}


@router.get("/chats/")
def my_chats(user=Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Chat).join(ChatParticipant).filter(ChatParticipant.user_id == user.id).all()

    def other_participants(chat):
        ids = [p.user_id for p in chat.participants if p.user_id != user.id]
        users = []
        from ..models import User as U
        for u in db.query(U).filter(U.id.in_(ids or [0])).all():
            users.append({"id": u.id, "name": f"{u.first_name} {u.last_name}".strip()})
        return users

    out = []
    for c in rows:
        last = c.messages[-1] if c.messages else None
        me = next(p for p in c.participants if p.user_id == user.id)
        unread_since = me.last_read_at or datetime.min
        unread = sum(1 for m in c.messages if m.sender_id != user.id and m.sent_at > unread_since)
        out.append({
            "id": c.id, "title": c.title, "is_group": bool(c.is_group),
            "program_id": c.program_id,
            "participants": other_participants(c),
            "last_message": {"body": last.body, "sent_at": str(last.sent_at),
                             "sender_id": last.sender_id} if last else None,
            "unread": unread,
        })
    return out


class MessageIn(BaseModel):
    body: str


@router.post("/chats/{chat_id}/messages/")
def send_message(chat_id: int, data: MessageIn, ctx=Depends(require_perm("chat.use"))):
    db: Session = ctx["db"]
    chat = db.get(Chat, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")
    is_member = db.query(ChatParticipant).filter_by(chat_id=chat.id, user_id=ctx["user"].id).first()
    if not is_member:
        raise HTTPException(status_code=403, detail="You do not have permission to perform this action.")
    m = ChatMessage(chat_id=chat.id, sender_id=ctx["user"].id, body=data.body)
    db.add(m)
    db.commit()
    db.refresh(m)
    return {"id": m.id, "sender_id": m.sender_id, "body": m.body, "sent_at": str(m.sent_at)}


@router.get("/chats/{chat_id}/messages/")
def chat_messages(chat_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    chat = db.get(Chat, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")
    member = db.query(ChatParticipant).filter_by(chat_id=chat.id, user_id=user.id).first()
    if not member:
        raise HTTPException(status_code=403, detail="You do not have permission to perform this action.")
    member.last_read_at = datetime.utcnow()
    db.commit()
    return [{
        "id": m.id, "sender_id": m.sender_id,
        "sender_name": f"{m.sender.first_name} {m.sender.last_name}".strip(),
        "body": m.body, "sent_at": str(m.sent_at),
    } for m in chat.messages]


# ------------------------------------------------------------------ notifications

@router.get("/notifications/")
def notifications(user=Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Notification).filter_by(user_id=user.id).order_by(
        Notification.created_at.desc()).limit(50).all()
    return [{
        "id": n.id, "type": n.type, "payload": n.payload, "read": n.read,
        "created_at": str(n.created_at)} for n in rows]


@router.post("/notifications/read-all/")
def read_all_notifications(user=Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(Notification).filter_by(user_id=user.id).update({"read": True})
    db.commit()
    return {"detail": "ok"}
