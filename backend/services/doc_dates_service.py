"""
SkillMe — Internship dates printed on the documents.

One rule, used everywhere a date is printed (offer letter, certificate, LOR, verify page,
PDF, certificate email):

    joining date    = batches.start_date (the enrollment start)
    completion date = joining date + exactly one calendar month

The completion date can be in the future: it is the end of the internship period, not the
day the certificate was claimed. The certificate and LOR are dated with it.

A student who holds a certificate may move their joining date *earlier* from the dashboard,
so that the completion date lands no later than the day they claimed the certificate. The
window is:

    earliest = (date the certificate was issued) - 1 month   (never later than the original)
    latest   = the original joining date

The first change records the original in batches.original_start_date, so the window never
drifts, and a student can move back to any date inside it.
"""

from __future__ import annotations

import calendar
import logging
from datetime import date, datetime

from db.database import db

logger = logging.getLogger("skillme.doc_dates")


class DocDatesError(Exception):
    """A change that can't be made. `status` is the HTTP status."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def parse_day(value) -> date | None:
    """'2026-11-20', '2026-11-20 10:00:00', ISO strings, date or datetime -> date."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def shift_months(d: date, months: int) -> date:
    """Calendar-month shift, clamped to the month's last day (31 Jan + 1 month = 28/29 Feb)."""
    total = d.month - 1 + months
    year, month = d.year + total // 12, total % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def internship_period(start_date, issued_at=None) -> tuple[date, date]:
    """(joining date, completion date). Without a stored start, the period ends on the
    issue date (legacy rows)."""
    start = parse_day(start_date)
    if start is None:
        end = parse_day(issued_at) or datetime.utcnow().date()
        return shift_months(end, -1), end
    return start, shift_months(start, 1)


def fmt_long(d: date) -> str:
    """'20 November 2026' (used in PDFs and emails)."""
    return f"{d.day} {d.strftime('%B %Y')}"


def period_fields(start_date, issued_at=None) -> dict:
    """The API fields every document endpoint returns."""
    start, end = internship_period(start_date, issued_at)
    return {"start_date": start.isoformat(), "end_date": end.isoformat()}


async def _context(student_id: int, batch_id: int) -> dict | None:
    return await db.fetch_one(
        """SELECT b.id AS batch_id, b.start_date, b.original_start_date, c.issued_at,
                  (SELECT COUNT(*) FROM enrollments e WHERE e.batch_id = b.id) AS members
           FROM certificates c JOIN batches b ON b.id = c.batch_id
           WHERE c.student_id = ? AND c.batch_id = ?
             -- Only after the certificate is paid for AND issued
             AND EXISTS (SELECT 1 FROM payments p WHERE p.student_id = c.student_id
                         AND p.batch_id = c.batch_id AND p.status = 'paid')""",
        (student_id, batch_id),
    )


def _window(row: dict) -> tuple[date, date] | None:
    original = parse_day(row["original_start_date"]) or parse_day(row["start_date"])
    issued = parse_day(row["issued_at"])
    if original is None or issued is None:
        return None
    return min(original, shift_months(issued, -1)), original


async def doc_dates_status(student_id: int, batch_id: int | None) -> dict | None:
    """What the dashboard's dates card needs. None when there is no certificate yet."""
    if not batch_id:
        return None
    row = await _context(student_id, batch_id)
    if not row:
        return None
    start, end = internship_period(row["start_date"], row["issued_at"])
    window = _window(row)
    original = parse_day(row["original_start_date"]) or parse_day(row["start_date"])
    can_edit = bool(window) and window[0] < window[1] and int(row["members"] or 0) == 1
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "original_start_date": original.isoformat() if original else None,
        "issued_date": (parse_day(row["issued_at"]) or end).isoformat(),
        "min_start": window[0].isoformat() if window else None,
        "max_start": window[1].isoformat() if window else None,
        "can_edit": can_edit,
        "changed": bool(row["original_start_date"]) and row["original_start_date"] != row["start_date"],
    }


async def change_start_date(student_id: int, batch_id: int, new_start: str) -> dict:
    """Move the joining date inside the allowed window. Returns the new status."""
    row = await _context(student_id, batch_id)
    if not row:
        raise DocDatesError(409, "Your dates can be changed once your certificate has been paid for and issued.")
    if int(row["members"] or 0) != 1:
        raise DocDatesError(409, "Your dates can't be changed online. Email admin@skill-me-intern.in and we'll fix them.")
    window = _window(row)
    if not window:
        raise DocDatesError(409, "Your dates can't be changed online. Email admin@skill-me-intern.in and we'll fix them.")
    day = parse_day(new_start)
    if day is None:
        raise DocDatesError(400, "Please pick a valid date.")
    lo, hi = window
    if day < lo or day > hi:
        raise DocDatesError(
            400,
            f"Pick a joining date between {fmt_long(lo)} and {fmt_long(hi)}.",
        )

    end = shift_months(day, 1)
    await db.execute(
        """UPDATE batches
           SET original_start_date = COALESCE(original_start_date, start_date),
               start_date = ?, end_date = ?, updated_at = CURRENT_TIMESTAMP
           WHERE id = ?""",
        (day.isoformat(), end.isoformat(), row["batch_id"]),
    )
    logger.info("Student #%s moved joining date of enrollment %s: %s -> %s",
                student_id, row["batch_id"], row["start_date"], day.isoformat())
    return await doc_dates_status(student_id, row["batch_id"])
