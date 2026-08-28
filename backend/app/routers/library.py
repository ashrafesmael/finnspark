import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..config import config
from ..database import get_db
from ..deps import require_branch_access, require_perm
from ..models import Document

router = APIRouter(tags=["library"])


@router.get("/branch/{branch_id}/documents/")
def list_documents(branch_id: int, request: Request, ctx=Depends(require_perm("library.view"))):
    db: Session = ctx["db"]
    q = db.query(Document).filter(Document.branch_id == branch_id)
    if v := request.query_params.get("program"):
        q = q.filter((Document.program_id == int(v)) | (Document.program_id.is_(None)))
    if v := request.query_params.get("business"):
        q = q.filter(Document.business_id == int(v))
    rows = q.order_by(Document.created_at.desc()).all()
    return [{
        "id": d.id, "name": d.name, "mime": d.mime, "size": d.size,
        "program_id": d.program_id, "business_id": d.business_id,
        "uploaded_by": d.uploaded_by_id, "created_at": str(d.created_at or ""),
    } for d in rows]


@router.post("/branch/{branch_id}/documents/")
async def upload_document(
    branch_id: int,
    file: UploadFile = File(...),
    name: str = Form(None),
    program_id: int = Form(None),
    business_id: int = Form(None),
    ctx=Depends(require_perm("library.edit")),
):
    db: Session = ctx["db"]
    uploads_dir = os.path.join(config.MEDIA_DIR, "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    ext = os.path.splitext(file.filename or "")[1][:20]
    stored = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(uploads_dir, stored)
    size = 0
    with open(path, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            out.write(chunk)
    doc = Document(
        branch_id=branch_id, name=name or file.filename or stored,
        file_path=f"uploads/{stored}", mime=file.content_type or "", size=size,
        program_id=program_id if program_id else None,
        business_id=business_id if business_id else None,
        uploaded_by_id=ctx["user"].id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return {"id": doc.id, "name": doc.name, "size": doc.size, "mime": doc.mime}


@router.get("/documents/{document_id}/download/")
def download_document(document_id: int, ctx=Depends(require_perm("library.view"))):
    db: Session = ctx["db"]
    doc = db.get(Document, document_id)
    if not doc or doc.branch_id != ctx["branch_id"]:
        raise HTTPException(status_code=404, detail="Not found.")
    path = os.path.join(config.MEDIA_DIR, doc.file_path)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File missing on disk.")
    return FileResponse(path, filename=doc.name, media_type=doc.mime or "application/octet-stream")


@router.delete("/branch/{branch_id}/documents/{document_id}/")
def delete_document(branch_id: int, document_id: int, ctx=Depends(require_perm("library.edit"))):
    db: Session = ctx["db"]
    doc = db.get(Document, document_id)
    if not doc or doc.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Not found.")
    try:
        os.remove(os.path.join(config.MEDIA_DIR, doc.file_path))
    except OSError:
        pass
    db.delete(doc)
    db.commit()
    return {"detail": "Deleted"}
