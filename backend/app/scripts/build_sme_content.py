"""Turn the extracted manual into LMS content (courses.json).

The extractor (extract_sme_manual.py) produces a chapter -> tip tree straight
from the PDF. This script maps that onto the LMS schema:

    course  = one chapter of the manual
    module  = a theme grouping inside the chapter (or a core/applied split)
    lesson  = one numbered tip
    block   = the tip's prose, plus one block per case study, self-check,
              worksheet or B2C/B2B variant sitting underneath it

Every block payload carries a ``kind`` so the learner interface can present each
kind differently -- a case study should not look like a self-check, and a
worksheet should not look like body copy. Before this existed, the kind was
encoded in the block title as a "Case study: ..." prefix and the UI had to parse
it back out again.

Usage
-----
    python3 app/scripts/build_sme_content.py \\
        app/content/sme_manual_extracted.json \\
        app/content/sme_manual_courses.json
"""

import html
import json
import os
import re
import sys

# node kind -> (block payload kind, label shown above the block, block type)
BLOCK_KINDS = {
    "case": ("case", "Case study", "text"),
    "checklist": ("checklist", "Self-check", "text"),
    "template": ("worksheet", "Worksheet", "text"),
    "section": ("practice", "In practice", "text"),
    "sub": ("variant", "", "text"),
}

CONTENT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "content")
DEFAULT_SRC = os.path.join(CONTENT_DIR, "sme_manual_extracted.json")
DEFAULT_OUT = os.path.join(CONTENT_DIR, "sme_manual_courses.json")

SOURCE_CREDIT = (
    "<p><em>Adapted from &ldquo;Successfully Operating a Business &ndash; "
    "The Manual&rdquo;, PUM Netherlands senior experts.</em></p>"
)


def to_html(text: str) -> str:
    """Plain extracted text -> paragraph HTML, with ampersands escaped once."""
    paragraphs = []
    for para in re.split(r"\n{2,}", text or ""):
        para = re.sub(r"(?<!\.)\n(?!\n)", " ", para)
        para = re.sub(r"[ \t]+", " ", para).strip()
        if para:
            paragraphs.append(f"<p>{html.escape(para)}</p>")
    return "".join(paragraphs)


def group_modules(lessons: list[dict]) -> list[dict]:
    """Chapters that carry theme sections get one module per theme; the rest are
    split into a core/applied pair so no module runs unmanageably long."""
    themed = [l for l in lessons
              if any(c["kind"] == "section" for c in l.get("children", []))]
    if themed:
        modules = []
        lead = [l for l in lessons if l not in themed]
        if lead:
            modules.append({"name": "Overview", "lessons": lead})
        for lesson in themed:
            theme = next(c["title"] for c in lesson["children"] if c["kind"] == "section")
            modules.append({"name": theme.title(), "lessons": [lesson]})
        return modules

    half = max(1, len(lessons) // 2)
    return [
        {"name": "Core advice", "lessons": lessons[:half]},
        {"name": "Applied practice", "lessons": lessons[half:]},
    ]


def build(chapters: list[dict]) -> list[dict]:
    courses = []
    for chapter in chapters:
        intro = chapter["intro"]
        intro_text = "\n\n".join(intro) if isinstance(intro, list) else (intro or "")

        # the chapter's own theme heading leads the description, so a card shows
        # what the chapter is about rather than the attribution line
        theme = chapter.get("theme") or ""
        lead = (f'<p class="kicker">{html.escape(theme.strip())}</p>' if theme else "")

        modules = []
        for module in group_modules(chapter["items"]):
            built_lessons = []
            for node in module["lessons"]:
                blocks = []
                if node["body"]:
                    blocks.append({
                        "block_type": "text",
                        "title": "",
                        "payload": {"html": to_html(node["body"]), "kind": "body"},
                        "order": 0,
                    })
                order = 1
                for child in node.get("children", []):
                    kind, label, block_type = BLOCK_KINDS.get(
                        child["kind"], ("related", "Related", "text"))
                    blocks.append({
                        "block_type": block_type,
                        "title": f"{label}: {child['title']}".strip(": ") if label else child["title"],
                        "payload": {"html": to_html(child["body"]), "kind": kind,
                                    "label": child["title"] if label else ""},
                        "order": order,
                    })
                    order += 1
                if not blocks:
                    continue

                title = node["title"]
                if node.get("number"):
                    title = f"{int(node['number']):02d}. {title}"
                built_lessons.append({
                    "name": title,
                    "description": "",
                    "blocks": blocks,
                })
            if built_lessons:
                modules.append({"name": module["name"], "description": "", "lessons": built_lessons})

        if not modules:
            continue

        number = int(chapter["number"])
        courses.append({
            "name": f"{number:02d}. {chapter['title']}",
            "description": (lead + to_html(intro_text) + SOURCE_CREDIT).strip(),
            "language": "en",
            "subtitle_languages": [],
            "program_id": None,
            "status": "published",
            "modules": modules,
        })
    return courses


def main() -> None:
    src = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SRC
    out = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUT
    with open(src, encoding="utf-8") as fh:
        chapters = json.load(fh)

    courses = build(chapters)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(courses, fh, ensure_ascii=False, indent=2)

    lessons = sum(len(m["lessons"]) for c in courses for m in c["modules"])
    blocks = [b for c in courses for m in c["modules"] for l in m["lessons"] for b in l["blocks"]]
    kinds = {}
    for b in blocks:
        kinds[b["payload"].get("kind")] = kinds.get(b["payload"].get("kind"), 0) + 1
    print(f"{len(courses)} courses, "
          f"{sum(len(c['modules']) for c in courses)} modules, "
          f"{lessons} lessons, {len(blocks)} blocks")
    print("block kinds:", dict(sorted(kinds.items(), key=lambda kv: -kv[1])))


if __name__ == "__main__":
    main()
