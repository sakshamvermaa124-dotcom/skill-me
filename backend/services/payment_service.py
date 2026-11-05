"""
SkillMe — Payment lifecycle transitions

Lifecycle:  created → pending → paid | failed        (abandoned is DERIVED at query time,
never stored: an order that is still created/pending after ABANDON_AFTER_MINUTES.)

Both the browser callback (/payments/verify) and the Razorpay webhook go through
these helpers, so a payment confirmed twice (or by both paths) is applied once.
"""

import logging

from db.database import db

logger = logging.getLogger("skillme.payments")

ABANDON_AFTER_MINUTES = 60


async def get_order(order_id: str) -> dict | None:
    return await db.fetch_one("SELECT * FROM payments WHERE razorpay_order_id = ?", (order_id,))


async def mark_paid(order_id: str, payment_id: str, via: str) -> tuple[dict | None, bool]:
    """
    Apply a successful payment to its order. Returns (order_row, newly_paid).
    Idempotent: an order that is already paid is left untouched (timestamps, payment id and
    confirmation channel keep their first values), and newly_paid is False so callers
    don't re-send emails.
    """
    order = await get_order(order_id)
    if not order:
        return None, False
    if order["status"] == "paid":
        return order, False
    await db.execute(
        """UPDATE payments
           SET razorpay_payment_id = ?, status = 'paid', confirmed_via = ?,
               failure_code = NULL, failure_reason = NULL,
               completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
           WHERE razorpay_order_id = ? AND status != 'paid'""",
        (payment_id, via, order_id),
    )
    return await get_order(order_id), True


async def mark_pending(order_id: str, payment_id: str | None = None) -> None:
    """Payment attempted/authorized but not yet captured. Never downgrades paid or failed-with-reason rows."""
    await db.execute(
        """UPDATE payments SET status = 'pending', razorpay_payment_id = COALESCE(?, razorpay_payment_id),
                  updated_at = CURRENT_TIMESTAMP
           WHERE razorpay_order_id = ? AND status IN ('created', 'pending', 'failed')""",
        (payment_id, order_id),
    )


async def mark_failed(order_id: str, code: str | None, reason: str | None) -> bool:
    """Record a failed attempt. A paid order is never overwritten. Returns True if a row changed."""
    order = await get_order(order_id)
    if not order or order["status"] == "paid":
        return False
    await db.execute(
        """UPDATE payments SET status = 'failed', failure_code = ?, failure_reason = ?,
                  updated_at = CURRENT_TIMESTAMP
           WHERE razorpay_order_id = ? AND status != 'paid'""",
        ((code or "")[:100] or None, (reason or "")[:300] or None, order_id),
    )
    return True
