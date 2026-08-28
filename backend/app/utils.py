from urllib.parse import urlencode

from fastapi.responses import JSONResponse


def serialize_ref(obj, lang: str = "en") -> dict:
    """Enums are returned as {id, name, code_name} (spec §8)."""
    return {"id": obj.id, "name": obj.name, "code_name": getattr(obj, "code_name", None)}


def loc(i18n_value, main_language: str = "en", lang: str = "en") -> str:
    """Resolve a multilingual JSON column to the requested language with fallback."""
    if isinstance(i18n_value, dict):
        return i18n_value.get(lang) or i18n_value.get(main_language) or i18n_value.get("en") or ""
    return i18n_value or ""


def paginate(items_query, page: int = 1, page_size: int = 20, serializer=None):
    """DRF-style envelope {count, next, previous, results} (spec §8)."""
    count = items_query.order_by(None).count()
    offset = (page - 1) * page_size
    rows = items_query.offset(offset).limit(page_size).all()
    results = [serializer(r) for r in rows] if serializer else rows

    def page_url(p):
        if p < 1 or (p - 1) * page_size >= count:
            return None
        return f"?{urlencode({'page': p, 'page_size': page_size})}"

    return {
        "count": count,
        "next": page_url(page + 1),
        "previous": page_url(page - 1),
        "results": results,
    }


def error(status: int, detail: str):
    return JSONResponse(status_code=status, content={"detail": detail})


def parse_page(request) -> tuple[int, int]:
    try:
        page = max(1, int(request.query_params.get("page", 1)))
    except ValueError:
        page = 1
    try:
        size = min(200, max(1, int(request.query_params.get("page_size", 20))))
    except ValueError:
        size = 20
    return page, size
