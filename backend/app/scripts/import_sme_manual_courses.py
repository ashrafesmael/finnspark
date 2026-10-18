"""Load the PUM 'Successfully Operating a Business' manual into the LMS.

The content file is generated from the source PDF by
``app/scripts/extract_sme_manual.py`` and mirrors the chapter structure of the
manual:

    course  = one chapter
    module  = a theme grouping inside the chapter (or a core/applied split)
    lesson  = one numbered tip
    block   = the tip's prose, plus a block per case study, self-check,
              worksheet or B2C/B2B variant that sits under it

Usage
-----
    # show what would change, touch nothing
    python3 app/scripts/import_sme_manual_courses.py --dry-run

    # write it (requires --apply, so it can never run by accident)
    python3 app/scripts/import_sme_manual_courses.py --apply

    # scope it to one programme instead of making the courses branch-wide
    python3 app/scripts/import_sme_manual_courses.py --apply --program-id 1

The import is idempotent: a course whose name already exists is updated in place
rather than duplicated, so it can be re-run after the content file is regenerated.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.database import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Branch, ContentBlock, Course, CourseStatus, Lesson, Module,
)

CONTENT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "content", "sme_manual_courses.json",
)


def chapter_number(name: str):
    """Leading chapter index of a course name, e.g. '03. Finances' -> 3."""
    m = re.match(r"^(\d+)\.\s", name or "")
    return int(m.group(1)) if m else None


def load_courses(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_structure(course: Course, modules: list[dict]) -> None:
    course.modules = []
    for m_order, mod in enumerate(modules):
        module = Module(name=mod["name"], description=mod.get("description", ""), order=m_order)
        for l_order, les in enumerate(mod.get("lessons", [])):
            lesson = Lesson(name=les["name"], description=les.get("description", ""),
                            order=l_order)
            for b_order, blk in enumerate(les.get("blocks", [])):
                lesson.blocks.append(ContentBlock(
                    block_type=blk.get("block_type", "text"),
                    title=blk.get("title", ""),
                    payload=blk.get("payload", {}),
                    order=blk.get("order", b_order),
                ))
            module.lessons.append(lesson)
        course.modules.append(module)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="write to the database (default is a dry run)")
    parser.add_argument("--dry-run", action="store_true", help="no-op; kept for clarity")
    parser.add_argument("--branch-id", type=int, default=1)
    parser.add_argument("--program-id", type=int, default=None,
                        help="attach the courses to a programme instead of branch-wide")
    parser.add_argument("--status", default="published")
    parser.add_argument("--content", default=CONTENT_PATH)
    args = parser.parse_args()

    courses = load_courses(args.content)
    db = SessionLocal()
    try:
        branch = db.get(Branch, args.branch_id)
        if not branch:
            print(f"branch {args.branch_id} not found", file=sys.stderr)
            return
        status = db.query(CourseStatus).filter(CourseStatus.code_name == args.status).first()

        existing = {
            c.name: c for c in db.query(Course).filter(Course.branch_id == args.branch_id).all()
        }
        # Courses are keyed by their chapter number as well as their name, so that
        # renumbering ("1. ..." -> "01. ...") updates in place instead of creating
        # a second copy alongside the old one.
        by_chapter = {}
        for c in existing.values():
            chapter = chapter_number(c.name)
            if chapter is not None:
                by_chapter[chapter] = c

        created = updated = 0
        for payload in courses:
            name = payload["name"]
            lessons = sum(len(m.get("lessons", [])) for m in payload.get("modules", []))
            blocks = sum(len(l.get("blocks", [])) for m in payload.get("modules", [])
                         for l in m.get("lessons", []))
            chapter = chapter_number(name)
            course = existing.get(name) or by_chapter.get(chapter)
            action = "update" if course else "create"
            print(f"  [{action:>6}] {name:<42} "
                  f"{len(payload['modules'])} modules, {lessons} lessons, {blocks} blocks")

            if not args.apply:
                created += action == "create"
                updated += action == "update"
                continue

            if course is None:
                course = Course(branch_id=args.branch_id)
                db.add(course)
                created += 1
            else:
                updated += 1
            course.name = name
            course.description = payload.get("description", "")
            course.language = payload.get("language", "en")
            course.subtitle_languages = payload.get("subtitle_languages", [])
            course.program_id = args.program_id
            course.status_id = status.id if status else course.status_id
            write_structure(course, payload.get("modules", []))

        if args.apply:
            db.commit()
            print(f"\ncommitted: {created} created, {updated} updated")
        else:
            print(f"\ndry run - nothing written. "
                  f"Would create {created}, update {updated}. Re-run with --apply.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
