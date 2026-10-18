"""Extract the Loans Repayments register (OCIF Track II, Cohorts 2 & 3) from
the PDF into an Excel file matching the repayment-batch upload template.

The register is a continued table: the column header appears only on the first
page, so column bounds detected there are reused for every page. Rows are
anchored on their date word. Two columns -- Loan # and Paid by -- suffer from
overlapping text runs (a restructure note kerned into the payer name), so those
two cells are rebuilt from character runs grouped by exact baseline, which
separates runs only 0.3pt apart where word extraction merges them.

Usage
-----
    python3 app/scripts/extract_repayments_register.py \\
        "../Loans Repayments.pdf" "../Loans Repayments (register).xlsx"
"""

import re
import sys
from datetime import datetime

import pdfplumber

DATE_RE = re.compile(r"(\d{1,2}-[A-Za-z]{3}-\d{4})")
AMOUNT_RE = re.compile(r"^[\d,]+\.\d{2}$")
NUM_SPLIT = re.compile(r"^([\d,]+\.\d{2})(.*)$", re.S)

HEADER_TOKENS = ["Cohor", "Startup", "Loan", "Paid", "Date", "Cash", "Channel",
                 "Amount", "Amount", "Instalment", "Verified"]
FIELDS = ["cohort", "startup", "loan_number", "payer_name", "date", "cash_bank",
          "channel", "amount_jod", "amount_eur", "instalment", "verified_against"]


def collapse(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def clean_amount(s: str) -> str:
    s = collapse(s).replace(",", "")
    if not s or s in ("-", "\u2014"):
        return ""
    return s


def header_starts(words, first_row_y):
    band = [w for w in words if first_row_y - 22 <= w["top"] <= first_row_y - 1.5]
    starts, last_x = [], -1.0
    for token in HEADER_TOKENS:
        cand = [w for w in band if w["text"].startswith(token) and w["x0"] > last_x]
        if not cand:
            return None
        starts.append(cand[0]["x0"])
        last_x = cand[0]["x0"]
    return list(zip(starts, FIELDS))


def column_text(page, y0, y1, x_from, x_to, prefer="letters"):
    """Text of a column region, rebuilt from character runs.

    Chars are grouped by exact baseline (0.1pt): overlapping runs at nearly
    the same y stay separate. Within a baseline, chars are joined in x order.
    The baseline whose character mix best matches the column wins -- the payer
    column is prose, the loan column carries the loan number, so a kerned note
    fragment from the neighbouring run never masquerades as the cell value.
    """
    chars = [c for c in page.chars
             if y0 <= c["top"] <= y1 and c["x1"] > x_from and c["x0"] < x_to]
    if not chars:
        return ""
    lines = {}
    for c in chars:
        lines.setdefault(round(c["top"], 1), []).append(c)
    best, best_score = "", -1.0
    for _, cs in sorted(lines.items()):
        cs = sorted(cs, key=lambda c: c["x0"])
        text = "".join(c["text"] for c in cs)
        if not text:
            continue
        if prefer == "digits":
            score = sum(ch.isdigit() for ch in text) / len(text)
        else:
            score = sum(ch.isalpha() for ch in text) / len(text)
        if score > best_score:
            best, best_score = text, score
    return collapse(best)


def total_line_ys(words):
    """Y positions of the register's per-startup 'X - total  n payment(s)'
    summary lines. They sit much closer to the row above (about 9pt) than the
    row pitch (15pt), so their words must be kept out of that row's window."""
    ys = set()
    for w in words:
        if w["text"] in ("payment(s)", "total", "GRAND", "TOTAL"):
            ys.add(round(w["top"], 1))
    return sorted(ys)


def page_rows(page, bounds):
    """Data rows of one page as field dicts, using the given column bounds."""
    words = page.extract_words()
    date_words = [w for w in words if DATE_RE.search(w["text"])]
    if not date_words:
        return []
    totals = total_line_ys(words)
    anchors = sorted({round(w["top"], 1) for w in date_words})
    bmap = dict(bounds)
    x = {f: s for s, f in bounds}
    ordered = sorted(bounds, key=lambda p: p[0])

    rows = []
    for i, ay in enumerate(anchors):
        nxt = anchors[i + 1] - 1.5 if i + 1 < len(anchors) else ay + 30
        row_words = [w for w in words if ay - 1.5 <= w["top"] < nxt
                     and not any(abs(w["top"] - ty) <= 1.5 for ty in totals)]
        cells = {f: [] for _, f in bounds}
        for w in sorted(row_words, key=lambda w: (round(w["top"], 1), w["x0"])):
            text = w["text"]
            m = DATE_RE.search(text)
            if m:  # date kerned into the next cell, e.g. '20-Jul-2025Cash'
                tail = text[m.end():].strip()
                cells["date"].append(m.group(1))
                if tail:
                    cells["cash_bank" if tail.startswith(("Cash", "Bank")) else "channel"].append(tail)
                continue
            if text and text[0].isdigit():
                m2 = NUM_SPLIT.match(text)
                if m2 and m2.group(2).strip():
                    _place(m2.group(1), w["x0"], ordered, cells)
                    tail_x = next((s for s, _ in ordered if s > w["x0"] + 1.5), w["x0"])
                    cells[_field_for(tail_x, ordered)].append(m2.group(2).strip())
                    continue
            _place(text, w["x0"], ordered, cells)

        row = {f: collapse(" ".join(v)) for f, v in cells.items()}
        # Loan # and Paid by are rebuilt from character runs: a restructure note
        # set across the payer column interleaves with the name at word level
        # the restructure note runs past the payer column, so the loan cell
        # extends to the date column and is told apart from the payer name by
        # its digits rather than by the column boundary
        row["loan_number"] = column_text(page, ay - 1.5, ay + 9,
                                         x["loan_number"] - 1, x["date"] - 1,
                                         prefer="digits")
        row["payer_name"] = column_text(page, ay - 1.5, ay + 9,
                                        x["payer_name"] - 0.5, x["date"] - 1)
        rows.append(row)
    return rows


def _field_for(x, ordered):
    for i in range(len(ordered) - 1, -1, -1):
        if x >= ordered[i][0] - 1.5:
            return ordered[i][1]
    return ordered[0][1]


def _place(text, x0, ordered, cells):
    cells[_field_for(x0, ordered)].append(text)


def main():
    pdf_path, out_path = sys.argv[1], sys.argv[2]
    rows = []
    with pdfplumber.open(pdf_path) as pdf:
        bounds = None
        for pi, page in enumerate(pdf.pages, 1):
            words = page.extract_words()
            date_words = [w for w in words if DATE_RE.search(w["text"])]
            if bounds is None and date_words:
                candidate = header_starts(words, min(w["top"] for w in date_words))
                if candidate:
                    bounds = candidate
            if bounds is None:
                continue
            for r in page_rows(page, bounds):
                if not r.get("date"):
                    continue
                if "total" in r.get("startup", "").lower() or "grand" in r.get("startup", "").lower():
                    continue
                r["page"] = pi
                rows.append(r)

    per_startup = {}
    for r in rows:
        key = r["startup"]
        jod = float(clean_amount(r["amount_jod"]) or 0)
        e = float(clean_amount(r["amount_eur"]) or 0)
        per_startup.setdefault(key, [0, 0.0, 0.0])
        per_startup[key][0] += 1
        per_startup[key][1] += jod
        per_startup[key][2] += e

    print(f"extracted {len(rows)} payment rows")
    for k, (n, jod, e) in per_startup.items():
        print(f"  {k[:38]:40} n={n:3}  JOD {jod:10,.2f}  EUR {e:10,.2f}")
    tot_jod = sum(v[1] for v in per_startup.values())
    tot_eur = sum(v[2] for v in per_startup.values())
    print(f"  {'TOTAL':40} n={len(rows):3}  JOD {tot_jod:10,.2f}  EUR {tot_eur:10,.2f}")

    with pdfplumber.open(pdf_path) as pdf:
        tail = pdf.pages[-1].extract_text() or ""
    m = re.search(r"GRAND TOTAL\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})", tail)
    if m:
        print(f"  register grand total:  JOD {float(m.group(1).replace(',', '')):,.2f}  "
              f"EUR {float(m.group(2).replace(',', '')):,.2f}")

    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Repayments"
    ws.append(["Cohort", "Startup", "Loan #", "Paid by", "Date of repayment",
               "Cash / Bank", "Channel", "Amount (JOD)", "Amount (EUR)",
               "Instalment / notes", "Verified against"])
    for r in rows:
        d = datetime.strptime(DATE_RE.search(r["date"]).group(1), "%d-%b-%Y").date()
        ws.append([
            r.get("cohort", ""), r.get("startup", ""), r.get("loan_number", ""),
            r.get("payer_name", ""), d.isoformat(),
            r.get("cash_bank", ""), r.get("channel", ""),
            float(clean_amount(r["amount_jod"]) or 0) or None,
            float(clean_amount(r["amount_eur"]) or 0) or None,
            r.get("instalment", ""), r.get("verified_against", ""),
        ])
    ws.freeze_panes = "A2"
    wb.save(out_path)
    print(f"written: {out_path}")


if __name__ == "__main__":
    main()
