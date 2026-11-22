"""AML screening of finnspark businesses and their founders via finnverify.

The manual "Screen now" action POSTs the business (and each founder) to the
finnverify machine-to-machine API on localhost; finnverify runs its full
screening (sanctions, PEP, adverse media, jurisdiction) and registers the
analysis, and the result (risk level, flags, report URL) is stored here against
the business.
"""
import logging
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import config
from ..database import get_db
from ..deps import require_branch_access
from ..models import Business, BusinessFounder, ScreeningRecord

logger = logging.getLogger(__name__)
router = APIRouter(tags=["screening"])


class ScreenNowIn(BaseModel):
    include_founders: bool = True
    country: str | None = None


def _screen_one(db: Session, business: Business, subject_type: str, name: str,
                country: str | None, user_id: int | None) -> ScreeningRecord:
    """Screen one subject via finnverify and store the result."""
    rec = ScreeningRecord(
        branch_id=business.branch_id, business_id=business.id,
        subject_type=subject_type, subject_name=name, status="queued",
        created_by_id=user_id)
    db.add(rec)
    db.flush()

    payload = {
        "entity_name": name,
        "entity_type": "organization" if subject_type == "business" else "individual",
        "reference": f"finnspark:{business.id}:{subject_type}",
        "callback_url": f"{config.PUBLIC_BASE_URL}/api/screening/{business.branch_id}/{business.id}/callback/",
        "callback_key": config.FINNVERIFY_API_KEY,
    }
    if subject_type == "business" and country:
        payload["country"] = country
    if subject_type == "individual" and country:
        payload["nationality"] = country

    try:
        r = httpx.post(
            f"{config.FINNVERIFY_API_URL}/integration/screen",
            json=payload,
            headers={"X-Portal-Key": config.FINNVERIFY_API_KEY},
            timeout=120.0,
        )
        data = r.json()
        if r.status_code != 200 or not data.get("ok"):
            raise RuntimeError(str(data.get("detail") or data)[:300])
        rec.analysis_id = data["analysis_id"]
        rec.risk_level = data["risk_level"]
        rec.risk_score = data.get("risk_score")
        rec.flags = data.get("flags") or []
        rec.report_url = data.get("report_url")
        rec.payload = data.get("analysis") or {}
        rec.status = "completed"
        rec.screened_at = datetime.utcnow()
    except Exception as e:
        rec.status = "failed"
        logger.exception("screening failed for %s (%s)", name, subject_type)
        rec.flags = [f"Screening failed: {e}"]
    return rec


@router.post("/screening/{branch_id}/{business_id}/screen-now/")
def screen_now(branch_id: int, business_id: int, data: ScreenNowIn | None = None,
               ctx=Depends(require_branch_access())):
    """Manual 'Screen now': screen the business and (optionally) each founder via
    finnverify. Synchronous — returns the full results for immediate display."""
    db: Session = ctx["db"]
    user = ctx["user"]
    data = data or ScreenNowIn()

    if not config.FINNVERIFY_API_KEY:
        raise HTTPException(status_code=503,
                            detail="Screening integration is not configured (FINNVERIFY_API_KEY missing).")

    business = db.get(Business, business_id)
    if not business or business.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Business not found.")

    records = []

    # the business itself (an organization)
    country = data.country
    records.append(_screen_one(db, business, "business", business.name, country, user.id))

    # each founder (an individual) — natural person screening
    if data.include_founders:
        for f in (business.founders or []):
            name = f"{f.first_name or ''} {f.last_name or ''}".strip()
            if name:
                records.append(_screen_one(db, business, "founder", name, country, user.id))

    db.commit()
    db.refresh(business)
    return {
        "ok": True,
        "business_id": business.id,
        "results": [_screening_ser(r) for r in records],
        "summary": {
            "highest_risk": _highest([r.risk_level for r in records]),
            "completed": sum(1 for r in records if r.status == "completed"),
            "failed": sum(1 for r in records if r.status == "failed"),
        },
    }


@router.get("/screening/{branch_id}/{business_id}/")
def screening_history(branch_id: int, business_id: int, ctx=Depends(require_branch_access())):
    db: Session = ctx["db"]
    rows = db.query(ScreeningRecord).filter(
        ScreeningRecord.branch_id == branch_id,
        ScreeningRecord.business_id == business_id,
    ).order_by(ScreeningRecord.created_at.desc()).limit(50).all()
    return {"results": [_screening_ser(r) for r in rows], "count": len(rows)}


RISK_ORDER = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}


def _highest(levels):
    levels = [l for l in levels if l]
    return max(levels, key=lambda l: RISK_ORDER.get(l, 0)) if levels else None


def _screening_ser(r: ScreeningRecord) -> dict:
    return {
        "id": r.id, "subject_type": r.subject_type, "subject_name": r.subject_name,
        "analysis_id": r.analysis_id, "risk_level": r.risk_level,
        "risk_score": r.risk_score, "flags": r.flags or [],
        "status": r.status, "report_url": r.report_url,
        "payload": r.payload or {},
        "screened_at": r.screened_at.isoformat() if r.screened_at else None,
    }
