"""Extract the 'finnpact Small Business Training Manual for Startup Entrepreneurs'
into LMS-ready content for the 'The Entrepreneur Journey' programme.

Usage
-----
    pdftotext -layout "finnpact Small Business Training Manual for Startup
    Entrepreneurs.pdf" /tmp/manual.txt
    python3 app/scripts/extract_entrepreneur_journey.py /tmp/manual.txt \
        app/content/entrepreneur_journey.json

The manual is cleanly typeset: 12 modules ("Module N: Title"), each with a short
intro, then four recurring sections — Key ideas / Ask yourself / Founder tips /
Action checklist. pdftotext -layout preserves the indentation, which is the
signal we parse on:

  * headings and body sit at 2 spaces, bullets at 8, wrapped bullet lines deeper;
  * a "Key ideas" lesson starts at a run-in heading ("Why startups fail. Common
    causes are ...") or a standalone heading ("The three statements at a glance") —
    both always follow a blank line, which separates them from wrapped prose.

Mapping into the LMS (same shape as sme_manual_courses.json):

    course  = one manual module ("EJ 01 — ...", numbered so it never collides
              with the PUM manual's chapter-keyed courses)
    module  = Introduction / Key ideas / Ask yourself / Founder tips / Action checklist
    lesson  = one key-idea heading, or one section lesson
    block   = text/html

Course names deliberately avoid a leading "N." so the chapter-keyed matching in
import_sme_manual_courses.py treats them as their own series.
"""
import html
import json
import re
import sys

PARTS = {
    1: "Foundations", 2: "Foundations",
    3: "Strategy & Market", 4: "Strategy & Market", 5: "Strategy & Market",
    6: "Financial Health", 7: "Financial Health", 8: "Financial Health",
    9: "Financial Health",
    10: "Planning & Funding", 11: "Planning & Funding",
    12: "Protection",
}

SECTION_MARKS = ("Key ideas", "Ask yourself", "Founder tips", "Action checklist")
MODULE_RE = re.compile(r"^\s*Module\s+(\d+):\s*(.+?)\s*$")
HEADER_RE = re.compile(r"finnpact Small Business Training Manual|^\s*Page \d+ of \d+\s*$")
RUNIN_RE = re.compile(r"^([A-Z][A-Za-z0-9 ,'&()/–-]{3,68}?[.:])\s+\S")


def paras(lines):
    """Group raw lines into paragraphs: (indent, text) items, blank-line separated."""
    out, cur = [], []
    for raw in lines:
        if not raw.strip():
            if cur:
                out.append(cur)
                cur = []
            continue
        stripped = raw.rstrip("\n")
        indent = len(stripped) - len(stripped.lstrip())
        cur.append((indent, stripped.strip()))
    if cur:
        out.append(cur)
    return out


def para_text(group):
    return " ".join(t for _, t in group)


def section_text(sec):
    """Join all paragraphs of a section (a list of paragraph groups) into one string."""
    return " ".join(para_text(g) for g in sec)


def indent_of(group):
    return group[0][0]


def to_html(text, items=None):
    body = html.escape(text)
    if items:
        lis = "".join(f"<li>{html.escape(i)}</li>" for i in items)
        body = f"<p>{body}</p><ul>{lis}</ul>"
    return f"<p>{body}</p>" if not items else body


def extract(txt_path, out_path):
    with open(txt_path, encoding="utf-8") as fh:
        raw = fh.readlines()
    lines = [l for l in raw if not HEADER_RE.search(l)]

    # split into modules
    modules, cur = [], None
    for l in lines:
        m = MODULE_RE.match(l)
        if m:
            cur = {"num": int(m.group(1)), "title": m.group(2).strip(), "lines": []}
            modules.append(cur)
        elif cur is not None:
            cur["lines"].append(l)
    assert len(modules) == 12, f"expected 12 modules, got {len(modules)}"

    courses = []
    for mod in modules:
        # split into section chunks at the four markers — markers are standalone
        # lines at 2-space indent, followed immediately by body (no blank line)
        chunks, cur_name, cur_lines = [], "Introduction", []
        for l in mod["lines"]:
            s = l.strip()
            if s in SECTION_MARKS and len(l) - len(l.lstrip()) == 2:
                chunks.append((cur_name, cur_lines))
                cur_name, cur_lines = s, []
                continue
            cur_lines.append(l)
        chunks.append((cur_name, cur_lines))
        chunks = [(nm, paras(sec)) for nm, sec in chunks if any(x.strip() for x in sec)]

        # course description = the module intro
        intro = next((section_text(sec) for nm, sec in chunks if nm == "Introduction" and sec), "")
        part = PARTS.get(mod["num"], "")
        desc = f"Part: {part}. " + intro if part else intro

        lms_modules = []
        intro_items = [para_text(g) for g in chunks[0][1]] if chunks and chunks[0][0] == "Introduction" else []
        lms_modules.append({
            "name": "Introduction",
            "description": "",
            "lessons": [{
                "name": f"Module {mod['num']} — {mod['title']}",
                "description": "",
                "blocks": [{"block_type": "text", "title": "", "order": 0,
                            "payload": {"html": to_html(intro)}}],
            }] if intro else [],
        })

        for sec_name, sec in chunks:
            if sec_name in ("Introduction",):
                continue
            if sec_name in ("Ask yourself", "Founder tips", "Action checklist"):
                items = [para_text(g) for g in sec if indent_of(g) >= 6]
                lms_modules.append({
                    "name": sec_name,
                    "description": "",
                    "lessons": [{
                        "name": sec_name,
                        "description": "",
                        "blocks": [{"block_type": "text", "title": "", "order": 0,
                                    "payload": {"html": to_html(
                                        {"Action checklist": "Before moving on, complete:",
                                         "Ask yourself": "Test your business against:",
                                         "Founder tips": "Practical advice:"}[sec_name], items)}}],
                    }],
                })
                continue

            # Key ideas -> split into lessons at run-in / standalone headings
            lessons, cur_les = [], None
            for gi, g in enumerate(sec):
                text = para_text(g)
                prev_blank = gi == 0 or True  # groups are blank-line separated already
                m = RUNIN_RE.match(text)
                standalone = (indent_of(g) <= 4 and len(text) <= 75
                              and not text.endswith((".", ",", ":", ";"))
                              and text[:1].isupper())
                if m:
                    title = m.group(1).rstrip(".:")
                    body = text[len(m.group(1)):].strip()
                    cur_les = {"name": title, "description": "",
                               "blocks": [{"block_type": "text", "title": "", "order": 0,
                                           "payload": {"html": to_html(body)}}]}
                    lessons.append(cur_les)
                elif standalone:
                    cur_les = {"name": text, "description": "",
                               "blocks": []}
                    lessons.append(cur_les)
                elif cur_les is not None:
                    cur_les["blocks"].append(
                        {"block_type": "text", "title": "", "order": len(cur_les["blocks"]),
                         "payload": {"html": to_html(text)}})
                else:
                    cur_les = {"name": "Overview", "description": "",
                               "blocks": [{"block_type": "text", "title": "", "order": 0,
                                           "payload": {"html": to_html(text)}}]}
                    lessons.append(cur_les)
            # merge trailing empty lessons
            lessons = [l for l in lessons if l["blocks"] or l["name"] != "Overview"]
            lms_modules.append({"name": "Key ideas", "description": "", "lessons": lessons})

        courses.append({
            "name": f"EJ {mod['num']:02d} — {mod['title']}",
            "description": desc,
            "language": "en",
            "subtitle_languages": [],
            "status": "published",
            "modules": [m for m in lms_modules if m["lessons"] or m["name"] != "Introduction"],
        })

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(courses, fh, ensure_ascii=False, indent=1)

    n_lessons = sum(len(m["lessons"]) for c in courses for m in c["modules"])
    n_blocks = sum(len(l["blocks"]) for c in courses for m in c["modules"] for l in m["lessons"])
    print(f"{len(courses)} courses, {n_lessons} lessons, {n_blocks} blocks -> {out_path}")


if __name__ == "__main__":
    extract(sys.argv[1], sys.argv[2])
