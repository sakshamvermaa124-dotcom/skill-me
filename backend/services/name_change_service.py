"""
SkillMe — Name changes
A student may correct the name printed on their documents (offer letter, certificate,
LOR, portfolio, emails) at most NAME_CHANGE_LIMIT times, and only until a certificate
is paid for or issued — after that it is on a publicly verifiable record.

The name belongs to the person, so it is stored once per application row but always
changed for every row sharing the email, and the limit counts across all of them.
Everything that shows a name (pages, PDFs, emails) reads students.first_name/last_name
at render/send time, so updating those rows is enough for it to show everywhere.
"""

import logging
import unicodedata

from db.database import db

logger = logging.getLogger("skillme.name_change")

NAME_CHANGE_LIMIT = 2
NAME_PART_MAX = 50
SUPPORT_EMAIL = "admin@skill-me-intern.in"

# Letters in any script, combining marks, spaces and the punctuation real names use.
_NAME_PUNCT = set(" .'’-")


class NameChangeError(Exception):
    """A change that can't be made. `status` is the HTTP status, `code` a stable reason."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def clean_name_part(raw: str | None, label: str) -> str:
    """Collapse whitespace and validate one part of a name. Raises NameChangeError with
    a message that can be shown to the student as-is."""
    value = " ".join((raw or "").split())
    if not value:
        raise NameChangeError(400, "invalid", f"Please enter your {label}.")
    if len(value) > NAME_PART_MAX:
        raise NameChangeError(400, "invalid", f"Your {label} can be at most {NAME_PART_MAX} characters.")
    for ch in value:
        if ch in _NAME_PUNCT or ch.isalpha() or unicodedata.category(ch).startswith("M"):
            continue
        raise NameChangeError(
            400, "invalid",
            f"Your {label} can only contain letters, spaces, hyphens, apostrophes and full stops.",
        )
    if not any(ch.isalpha() for ch in value):
        raise NameChangeError(400, "invalid", f"Your {label} must contain at least one letter.")
    return value


def _norm_email(email: str | None) -> str:
    return (email or "").strip().lower()


async def name_status(email: str) -> dict:
    """What the dashboard needs to render the name card."""
    key = _norm_email(email)
    locked = await db.fetch_one(
        """SELECT 1 AS locked FROM students s
           WHERE lower(s.email) = ?
             AND (EXISTS (SELECT 1 FROM payments p WHERE p.student_id = s.id AND p.status = 'paid')
                  OR EXISTS (SELECT 1 FROM certificates c WHERE c.student_id = s.id))
           LIMIT 1""",
        (key,),
    )
    used_row = await db.fetch_one("SELECT COUNT(*) AS n FROM name_changes WHERE email = ?", (key,))
    used = int(used_row["n"]) if used_row else 0
    remaining = max(0, NAME_CHANGE_LIMIT - used)
    if locked:
        reason = "certificate_issued"
    elif remaining == 0:
        reason = "limit_reached"
    else:
        reason = None
    return {
        "limit": NAME_CHANGE_LIMIT,
        "used": used,
        "remaining": remaining,
        "can_edit": reason is None,
        "locked_reason": reason,
    }


async def change_name(student_id: int, first_name: str, last_name: str) -> dict:
    """Validate and apply a name change for the person who owns `student_id`.
    Returns the new name, the previous one and the updated status."""
    row = await db.fetch_one(
        "SELECT email, first_name, last_name FROM students WHERE id = ?", (student_id,)
    )
    if not row:
        raise NameChangeError(404, "not_found", "Student not found.")

    first = clean_name_part(first_name, "first name")
    last = clean_name_part(last_name, "last name")
    old_first, old_last = (row["first_name"] or "").strip(), (row["last_name"] or "").strip()
    if (first, last) == (old_first, old_last):
        raise NameChangeError(400, "unchanged", "This is already the name on your documents.")

    status = await name_status(row["email"])
    if status["locked_reason"] == "certificate_issued":
        raise NameChangeError(
            409, "certificate_issued",
            f"Your name is locked because your certificate has been issued with it. "
            f"Email {SUPPORT_EMAIL} if it needs a correction.",
        )
    if status["locked_reason"] == "limit_reached":
        raise NameChangeError(
            409, "limit_reached",
            f"You've used both of your name changes. Email {SUPPORT_EMAIL} if it still needs a correction.",
        )

    key = _norm_email(row["email"])
    try:
        await db.insert(
            """INSERT INTO name_changes
               (email, student_id, change_number, old_first_name, old_last_name, new_first_name, new_last_name)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (key, student_id, status["used"] + 1, old_first, old_last, first, last),
        )
    except Exception as e:
        # Unique (email, change_number): another request took this change slot first.
        if "unique" in str(e).lower():
            raise NameChangeError(409, "conflict", "Your name was just changed from another tab. Refresh and try again.")
        raise

    await db.execute(
        """UPDATE students SET first_name = ?, last_name = ?, updated_at = CURRENT_TIMESTAMP
           WHERE lower(email) = ?""",
        (first, last, key),
    )
    logger.info(
        "Student #%s changed name (%s/%s): '%s %s' -> '%s %s'",
        student_id, status["used"] + 1, NAME_CHANGE_LIMIT, old_first, old_last, first, last,
    )
    return {
        "first_name": first,
        "last_name": last,
        "name": f"{first} {last}",
        "previous_name": f"{old_first} {old_last}".strip(),
        "email": row["email"],
        "name_change": await name_status(row["email"]),
    }


async def list_changes(q: str | None, page: int, limit: int) -> dict:
    """Admin history, newest first, with the person's current name and whether their
    name is now locked by a paid certificate."""
    where, params = "", []
    if q:
        like = f"%{q.strip().lower()}%"
        where = """WHERE nc.email LIKE ?
                      OR lower(nc.old_first_name || ' ' || nc.old_last_name) LIKE ?
                      OR lower(nc.new_first_name || ' ' || nc.new_last_name) LIKE ?"""
        params = [like, like, like]
    total_row = await db.fetch_one(f"SELECT COUNT(*) AS n FROM name_changes nc {where}", tuple(params))
    total = int(total_row["n"]) if total_row else 0
    rows = await db.fetch_all(
        f"""SELECT nc.id, nc.student_id, nc.email, nc.change_number,
                   nc.old_first_name, nc.old_last_name, nc.new_first_name, nc.new_last_name,
                   nc.changed_at,
                   (SELECT s.first_name || ' ' || s.last_name FROM students s
                     WHERE lower(s.email) = nc.email ORDER BY s.id LIMIT 1) AS current_name,
                   (SELECT s.domain FROM students s WHERE s.id = nc.student_id) AS domain,
                   EXISTS (SELECT 1 FROM students s JOIN payments p ON p.student_id = s.id
                            WHERE lower(s.email) = nc.email AND p.status = 'paid') AS paid
            FROM name_changes nc {where}
            ORDER BY nc.changed_at DESC, nc.id DESC
            LIMIT ? OFFSET ?""",
        tuple(params + [limit, (page - 1) * limit]),
    )
    stats = await db.fetch_one(
        """SELECT COUNT(*) AS changes,
                  COUNT(DISTINCT email) AS people,
                  (SELECT COUNT(*) FROM (SELECT email FROM name_changes GROUP BY email
                                         HAVING COUNT(*) >= ?)) AS maxed_out,
                  SUM(CASE WHEN changed_at >= datetime('now', '-7 days') THEN 1 ELSE 0 END) AS last_7_days
           FROM name_changes""",
        (NAME_CHANGE_LIMIT,),
    )
    return {
        "changes": [
            {
                **{k: r[k] for k in ("id", "student_id", "email", "change_number", "changed_at", "domain")},
                "old_name": f"{r['old_first_name']} {r['old_last_name']}".strip(),
                "new_name": f"{r['new_first_name']} {r['new_last_name']}".strip(),
                "current_name": (r["current_name"] or "").strip() or None,
                "paid": bool(r["paid"]),
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "total_pages": max(1, -(-total // limit)),
        "limit": NAME_CHANGE_LIMIT,
        "stats": {
            "changes": int((stats or {}).get("changes") or 0),
            "people": int((stats or {}).get("people") or 0),
            "maxed_out": int((stats or {}).get("maxed_out") or 0),
            "last_7_days": int((stats or {}).get("last_7_days") or 0),
        },
    }
