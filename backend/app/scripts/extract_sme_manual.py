"""Extract the PUM 'Successfully Operating a Business' manual into LMS-ready content.

Usage
-----
python3 extract_sme.py "SME Business Manual.pdf" content.json

Approach
--------
Rather than guessing headings from capitalisation -- which is fragile because the
manual is typeset in a design grid, stacks a heading over two lines and puts the
tip number on either of them -- this reads the PDF with pdfplumber and uses the
typeface itself as the signal:

  * body copy is set at ~9pt in a serif face;
  * a tip heading is the heavier weight at ~10pt, with its number at the left,
    centre or right of the same line band;
  * chapter openers ("3 Finances & Financing") are much larger and can span
    three short lines.

Consecutive heading lines are then merged into one title, page numbers dropped,
and the body text between headings collected verbatim.

Node kinds
----------
tip        numbered advice                   -> Lesson
section    unnumbered theme                   -> module grouping
sub        "B2C TIP" / "B2B TIP"             -> folded into the parent lesson
case       company story ("... IN JORDAN")    -> 'Case study' block
checklist  CHECK / CSR CHECKLIST             -> 'Self-check' block
template   "... PLANNING SHEET"               -> 'Worksheet' block
intro      chapter opening paragraphs         -> course introduction
"""

import collections
import json
import re
import sys

import pdfplumber

CHAPTERS = [
    (1, "Management & Organisation", 9, 17),
    (2, "Marketing & Sales", 17, 29),
    (3, "Finances & Financing", 29, 37),
    (4, "Efficiency & Logistics", 37, 45),
    (5, "HRM & Training", 45, 55),
    (6, "Technology & Quality", 55, 65),
    (7, "ICT & Information Supply", 65, 71),
    (8, "Innovation", 71, 77),
    (9, "Exporting", 77, 83),
    (10, "Corporate Social Responsibility", 83, 93),
    (11, "The Business Plan", 93, 105),
    (12, "Family Businesses", 105, 109),
    (13, "Anatomy of the good entrepreneur", 109, 112),
]

CASE_WORDS = re.compile(
    r"\bIN (JORDAN|INDONESIA|CHINA|KYRGYZSTAN|BOSNIA|EASTERN EUROPE|MOROCCO|TUNISIA|EGYPT|"
    r"KENYA|GHANA|SENEGAL|CAMEROON|YEMEN|SYRIA|IRAQ|PALESTINE|PERU|VIETNAM|BANGLADESH|INDIA|"
    r"UGANDA|TANZANIA|SOUTH AFRICA|NIGERIA|ETHIOPIA|RWANDA|ZAMBIA|ZIMBABWE|ECUADOR|COLOMBIA|"
    r"COSTA RICA|THAILAND|VENEZUELA|PARAGUAY|URUGUAY|BOLIVIA)\b|\bCASE\b")
CHECK_WORDS = re.compile(r"CHECK")
TEMPLATE_WORDS = re.compile(r"SHEET|WORKSHEET")
FOOTER = re.compile(r"PUM THE MANUAL|CONTENTS|EASTERN EUROPE")


def page_lines(page):
    """[(text, max_font_size, dominant_font)] for one page, top to bottom."""
    rows = {}
    for ch in page.chars:
        key = round(ch["top"], 0)
        rows.setdefault(key, []).append(ch)
    out = []
    for key in sorted(rows):
        chars = rows[key]
        chars.sort(key=lambda c: c["x0"])
        text = "".join(c["text"] for c in chars)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        biggest = max(c["size"] for c in chars)
        dominant = [c for c in chars if c["size"] >= biggest - 0.05]
        font = collections.Counter(c["fontname"] for c in dominant).most_common(1)[0][0]
        bold_digits = "".join(c["text"] for c in dominant
                              if c["fontname"].endswith("-700") and c["text"].strip().isdigit())
        tipnum = int(bold_digits) if bold_digits.isdigit() and 1 <= int(bold_digits) <= 10 else None
        out.append((text, round(biggest, 1), font, tipnum))
    return out


def tidy(text: str) -> str:
    text = text.replace("\u00ad", "").replace("\u2019", "'")
    text = re.sub(r"\s+", " ", text).strip()
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"\s+\d{1,3}\s+(?=[A-Z])", " ", text)
    text = re.sub(r"\s+\d{1,3}$", "", text)
    return text.strip(" .&—-").strip()


def classify(title: str, numbered: bool) -> str:
    up = title.upper()
    if up in ("B2C TIP", "B2B TIP"):
        return "sub"
    if CHECK_WORDS.search(up):
        return "checklist"
    if TEMPLATE_WORDS.search(up):
        return "template"
    if CASE_WORDS.search(up):
        return "case"
    return "tip" if numbered else "section"


def main():
    pdf_path, out_path = sys.argv[1], sys.argv[2]
    with pdfplumber.open(pdf_path) as pdf:
        pages = {}
        for i, page in enumerate(pdf.pages, start=1):
            pages[i] = page_lines(page)

    # the manual's own fonts decide what counts as a heading
    def embedded_number(text):
        """Tip numbers are sometimes set inline with the heading, e.g.
        '1START OUT WITH A GOOD CASHBOOK' or 'WATCH YOUR DEBTORS3'."""
        m = re.match(r"^(\d{1,2})\s*([A-Z].*)$", text)
        if m and 1 <= int(m.group(1)) <= 10:
            return int(m.group(1)), m.group(2).strip()
        m = re.match(r"^([A-Z].*?)\s*(\d{1,2})$", text)
        if m and 1 <= int(m.group(2)) <= 10 and len(m.group(1).split()) >= 2:
            return int(m.group(2)), m.group(1).strip()
        return None, text

    def is_chapter_opener(size):
        return size >= 20.0

    def is_heading(text, size, font):
        """Body copy is set in the Aldine serif at 9pt; every heading in the
        design grid is MuseoSansRounded at 14pt or larger."""
        # tips are 14-15.8pt, thematic headings 11pt, chapter standfirst 12pt;
        # body copy is the 9pt Aldine serif, which never reaches this branch
        if FOOTER.search(text) or size < 10.5:
            return False
        if "MuseoSansRounded" not in font:
            return False
        # standfirst prose uses the same face but is set in sentence case, so
        # the capitalisation ratio separates it from a heading
        if text.strip().isdigit():          # a set tip number on its own
            return True
        letters = [c for c in text if c.isalpha()]
        if len(letters) < 3 or sum(c.isupper() for c in letters) / len(letters) <= 0.6:
            return False
        return len(text.split()) <= 12

    chapters = []
    grand = 0
    for num, name, start, end in CHAPTERS:
        nodes, intro, theme = [], [], []
        body, pending = [], []
        open_head = None
        current = None

        def commit(parts, number):
            nonlocal current
            joined = " ".join(p for p in parts if p and not p.strip().isdigit())
            if number is None:
                m = re.match(r"^(\d{1,2})\s*(.+)$", joined)
                if m and 1 <= int(m.group(1)) <= 10:
                    number, joined = int(m.group(1)), m.group(2)
                else:
                    m = re.search(r"^(.+?)\s*(\d{1,2})$", joined)
                    if m and 1 <= int(m.group(2)) <= 10 and len(m.group(1).split()) >= 3:
                        number, joined = int(m.group(2)), m.group(1)
            title = tidy(joined)
            if len(title) < 4:
                return
            kind = classify(title, number is not None)
            if kind == "tip" or not nodes:
                # A theme heading that appears before any numbered tip is itself a
                # lesson: some chapters in the manual are thematic and carry no
                # tip numbers at all (12, 13).
                node = {"kind": "tip", "number": number, "title": title,
                        "body": [], "children": []}
                nodes.append(node)
                current = node
            else:
                child = {"kind": kind, "title": title, "body": [], "children": []}
                nodes[-1]["children"].append(child)
                current = child

        def close_head():
            nonlocal open_head
            if open_head:
                commit(open_head["parts"], open_head["number"])
                open_head = None

        def flush_body():
            nonlocal body
            if not body:
                return
            text = re.sub(r"[ \t]+", " ", "\n".join(body))
            text = re.sub(r"\n{3,}", "\n\n", text)
            text = re.sub(r"^\s*\d{1,3}\s*$", "", text, flags=re.M).strip()
            body = []
            # drop caps and page furniture leave one- or two-character rows
            if len(re.sub(r"\s", "", text)) < 25:
                return
            if current is not None:
                current["body"].append(text)
            elif nodes:
                nodes[-1]["body"].append(text)
            else:
                # still on the chapter's opening spread: this is its introduction
                intro.append(text)

        for pageno in range(start, end):
            for text, size, font, tipnum in pages.get(pageno, []):
                if is_chapter_opener(size):
                    flush_body()
                    close_head()
                    if pending:
                        commit(pending, None)
                        pending = []
                    continue
                # The chapter's own theme heading: all caps, set at standfirst
                # size on the opening spread, and carrying no tip number --
                # chapter 1's "TEN RULES FOR SUCCESSFULLY OPERATING A BUSINESS".
                # It introduces the chapter rather than opening a lesson, so
                # without this it swallowed the introduction and showed up as a
                # phantom first lesson with no guidance in it.
                if (not nodes and not pending and pageno == start
                        and tipnum is None and size < 13.5
                        and is_heading(text, size, font)):
                    theme.append(text)
                    continue
                if is_heading(text, size, font):
                    flush_body()
                    embedded, stripped = embedded_number(text)
                    number = tipnum if tipnum is not None else embedded
                    if embedded is not None:
                        text = stripped
                    if text.strip().isdigit():
                        text = ""            # the row carried only the tip number
                    if number is not None and 1 <= number <= 10:
                        close_head()
                        open_head = {"number": number,
                                     "parts": list(pending) + ([text] if text else [])}
                        pending = []
                    elif open_head is not None:
                        open_head["parts"].append(text)
                    else:
                        pending.append(text)
                    continue
                if not text or FOOTER.search(text):
                    continue
                close_head()
                if pending:
                    commit(pending, None)
                    pending = []
                body.append(text)
        close_head()
        flush_body()

        def prune(node):
            node["body"] = "\n\n".join(node["body"]).strip()
            # keep a heading that carries no prose of its own when it introduces
            # sub-blocks, otherwise the entire subtree is silently dropped
            node["children"] = [c for c in (prune(k) for k in node["children"])
                                if c["body"] or c.get("children")]
            if not node["children"]:
                node.pop("children")
            return node

        nodes = [n for n in (prune(node) for node in nodes)
                 if n["body"] or n.get("children")]

        # A chapter with no numbered tips at all is thematic: its section
        # headings are the lessons, not sub-blocks of an imaginary first lesson.
        if nodes and not any(n["number"] for n in nodes):
            promoted = []
            for n in nodes:
                kids = [c for c in n.get("children", []) if c["kind"] == "section" and c["body"]]
                others = [c for c in n.get("children", []) if c not in kids]
                if kids:
                    n["children"] = others
                    promoted.append(n)
                    for k in kids:
                        k.pop("kind", None)
                        promoted.append({"kind": "tip", "number": None,
                                         "title": k["title"], "body": k["body"],
                                         "children": others})
                else:
                    promoted.append(n)
            nodes = promoted

        counts, stack = {}, list(nodes)
        while stack:
            n = stack.pop()
            counts[n["kind"]] = counts.get(n["kind"], 0) + 1
            stack.extend(n.get("children", []))
        tips = counts.get("tip", 0) or 0
        grand += tips
        words = sum(len(n["body"].split()) for n in nodes) + sum(len(t.split()) for t in intro)
        chapters.append({
            "number": num, "title": name, "page_start": start, "page_end": end - 1,
            "theme": " ".join(theme).strip(), "intro": intro, "items": nodes,
        })
        detail = " ".join(f"{k}={v}" for k, v in sorted(counts.items()) if k != "tip")
        print(f"ch{num:>2} {name:<36} lessons={tips:>2} {detail:<40} ~{words}w",
              file=sys.stderr)

    json.dump(chapters, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"TOTAL lessons: {grand}", file=sys.stderr)


if __name__ == "__main__":
    main()
