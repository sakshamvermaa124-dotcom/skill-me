"""
SkillMe — Top-performer stipend entries

Only students who finished the internship and hold an issued certificate (paid for, or
issued by an admin) can enter the stipend round. They confirm their seat in one click:
the seat is tied to their own certificate, looked up from the signed-in account. (A typed
certificate ID is still accepted, for older clients.)

Anti-spam rules, enforced here and by UNIQUE constraints on stipend_entries:
  * one entry per person (email), across every track they applied to
  * a certificate can claim only one seat
  * the certificate must be issued to the signed-in person
"""

import logging
import re

from db.database import db

logger = logging.getLogger("skillme.stipend")

SUPPORT_EMAIL = "admin@skill-me-intern.in"
_CERT_BODY = re.compile(r"^[0-9A-Z]{12}$")


class StipendError(Exception):
    """An entry that can't be made. `status` is the HTTP status, `code` a stable reason."""

    def __init__(self, status: int, code: str, message: str, entry: dict | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.entry = entry


def normalize_cert_id(raw: str | None) -> str | None:
    """'sm a1b2 c3d4-e5f6' -> 'SM-A1B2-C3D4-E5F6'. None if it can't be a certificate ID."""
    s = re.sub(r"[^0-9A-Za-z]", "", raw or "").upper()
    if s.startswith("SM"):
        s = s[2:]
    if not _CERT_BODY.match(s):
        return None
    return f"SM-{s[:4]}-{s[4:8]}-{s[8:]}"


def _norm_email(email: str | None) -> str:
    return (email or "").strip().lower()


def _entry_out(row: dict | None) -> dict | None:
    if not row:
        return None
    return {"cert_id": row["cert_id"], "entered_at": row["entered_at"]}


async def _entry_for(email: str) -> dict | None:
    return await db.fetch_one(
        "SELECT cert_id, entered_at FROM stipend_entries WHERE email = ?", (_norm_email(email),)
    )


async def _own_certificate(key: str) -> dict | None:
    """The person's first issued certificate: the one their seat is tied to."""
    return await db.fetch_one(
        """SELECT c.cert_id, c.student_id, c.batch_id, s.email, s.first_name, s.last_name,
                  COALESCE(b.domain, s.domain) AS domain
           FROM certificates c
           JOIN students s ON s.id = c.student_id
           LEFT JOIN batches b ON b.id = c.batch_id
           WHERE lower(s.email) = ?
           ORDER BY c.issued_at, c.id LIMIT 1""",
        (key,),
    )


async def stipend_status(email: str) -> dict:
    """What the dashboard needs: is this person eligible, have they claimed their seat, and
    which of their certificates the seat is tied to (only ever their own)."""
    key = _norm_email(email)
    entry = await _entry_for(key)
    cert = await _own_certificate(key)
    return {
        "eligible": bool(cert), "entered": bool(entry), "entry": _entry_out(entry),
        "certificate": {"cert_id": cert["cert_id"], "domain": cert["domain"]} if cert else None,
    }


async def enter_stipend(email: str, raw_cert_id: str | None = None) -> dict:
    """Claim the person's one stipend seat with a certificate issued to them.
    Without a certificate ID, their own certificate is used (the one-click path).

    Returns {"entry": {...}, "student": {...}} where student holds what the confirmation email needs.
    Raises StipendError with a message that can be shown to the student as-is.
    """
    key = _norm_email(email)

    existing = await _entry_for(key)
    if existing:
        raise StipendError(
            409, "already_entered",
            "Your seat is already confirmed. Each student can enter the stipend round once.",
            entry=_entry_out(existing),
        )

    if not (raw_cert_id or "").strip():
        cert = await _own_certificate(key)
        if not cert:
            raise StipendError(
                403, "not_certified",
                "Seats are for interns who hold a SkillMe certificate. Issue yours from the Credentials tab first.",
            )
        return await _insert_entry(key, cert)

    cert_id = normalize_cert_id(raw_cert_id)
    if not cert_id:
        raise StipendError(
            400, "invalid_format",
            "That doesn't look like a certificate ID. It looks like SM-XXXX-XXXX-XXXX "
            "and is printed at the bottom of your certificate.",
        )

    cert = await db.fetch_one(
        """SELECT c.cert_id, c.student_id, c.batch_id, s.email, s.first_name, s.last_name,
                  COALESCE(b.domain, s.domain) AS domain
           FROM certificates c
           JOIN students s ON s.id = c.student_id
           LEFT JOIN batches b ON b.id = c.batch_id
           WHERE c.cert_id = ?""",
        (cert_id,),
    )
    if not cert:
        raise StipendError(
            404, "not_found",
            "We couldn't find a certificate with that ID. Check it against your certificate and try again.",
        )
    if _norm_email(cert["email"]) != key:
        raise StipendError(
            403, "not_yours",
            "This certificate was issued to someone else. Enter the ID from your own certificate.",
        )
    return await _insert_entry(key, cert)


async def _insert_entry(key: str, cert: dict) -> dict:
    cert_id = cert["cert_id"]
    try:
        await db.insert(
            "INSERT INTO stipend_entries (email, student_id, batch_id, cert_id) VALUES (?, ?, ?, ?)",
            (key, cert["student_id"], cert["batch_id"], cert_id),
        )
    except Exception as e:
        # Two simultaneous submissions: the UNIQUE constraint lets only one through.
        if "unique" in str(e).lower():
            raise StipendError(
                409, "already_entered",
                "Your seat is already confirmed. Each student can enter the stipend round once.",
                entry=_entry_out(await _entry_for(key)),
            )
        raise

    entry = await _entry_for(key)
    logger.info(f"Stipend seat confirmed for {key} with {cert_id}")
    return {"entry": _entry_out(entry), "student": cert}
