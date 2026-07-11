"""Month-over-month comparison/classification engine.

For every fund that actually reported holdings in the target ref_date, diff
its current holdings against its own most recent PRIOR reporting month (not a
fixed "target minus one calendar month") — this tolerates funds that skip a
month of reporting without producing false CLOSED/DECREASED noise. Funds that
do not report at all in the target month are simply absent from this run's
output; their movements resume whenever they report again. This is the
"passive" fund-closure-detection behavior documented in the plan.

Implemented as one set-based SQL pass (CTEs + FULL OUTER JOIN) per month
rather than looping per fund in application code, per the design in
docs/DATA_SOURCES.md / the approved plan.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import FundAssetMovement, MovementClassification

logger = logging.getLogger(__name__)

# Guards against float/decimal rounding noise showing up as a spurious
# INCREASED/DECREASED when a position is effectively unchanged.
QTY_EPSILON = Decimal("0.000001")

_DIFF_SQL = text(
    """
    WITH funds_this_month AS (
        SELECT DISTINCT fund_id FROM fund_holdings WHERE ref_date = :target_date
    ),
    fund_prior_date AS (
        SELECT fh.fund_id, MAX(fh.ref_date) AS prior_ref_date
        FROM fund_holdings fh
        JOIN funds_this_month f ON f.fund_id = fh.fund_id
        WHERE fh.ref_date < :target_date
        GROUP BY fh.fund_id
    ),
    current_h AS (
        SELECT fund_id, asset_id, quantity, market_value
        FROM fund_holdings
        WHERE ref_date = :target_date
    ),
    prior_h AS (
        SELECT h.fund_id, h.asset_id, h.quantity, h.market_value
        FROM fund_holdings h
        JOIN fund_prior_date p ON p.fund_id = h.fund_id AND h.ref_date = p.prior_ref_date
    )
    SELECT
        COALESCE(c.fund_id, pr.fund_id) AS fund_id,
        COALESCE(c.asset_id, pr.asset_id) AS asset_id,
        c.quantity AS qty_current, pr.quantity AS qty_prior,
        c.market_value AS value_current, pr.market_value AS value_prior,
        fpd.prior_ref_date AS prior_ref_date
    FROM current_h c
    FULL OUTER JOIN prior_h pr ON pr.fund_id = c.fund_id AND pr.asset_id = c.asset_id
    LEFT JOIN fund_prior_date fpd ON fpd.fund_id = COALESCE(c.fund_id, pr.fund_id)
    """
)


def _classify(qty_current: Decimal | None, qty_prior: Decimal | None) -> MovementClassification:
    if qty_prior is None:
        return MovementClassification.NEW
    if qty_current is None:
        return MovementClassification.CLOSED
    delta = qty_current - qty_prior
    if delta > QTY_EPSILON:
        return MovementClassification.INCREASED
    if delta < -QTY_EPSILON:
        return MovementClassification.DECREASED
    return MovementClassification.UNCHANGED


def compute_movements(db: Session, ref_date: date) -> int:
    """Compute and upsert fund_asset_movements for one ref_date. Idempotent —
    safe to re-run (e.g. after a same-month CDA re-ingestion during its daily
    refresh window); values are recomputed and upserted, not appended."""
    rows = db.execute(_DIFF_SQL, {"target_date": ref_date}).mappings().all()

    movement_rows = []
    for r in rows:
        qty_current = r["qty_current"]
        qty_prior = r["qty_prior"]
        value_current = r["value_current"] if r["value_current"] is not None else Decimal("0")
        value_prior = r["value_prior"] if r["value_prior"] is not None else Decimal("0")

        classification = _classify(qty_current, qty_prior)

        qty_current_eff = qty_current if qty_current is not None else Decimal("0")
        qty_prior_eff = qty_prior if qty_prior is not None else Decimal("0")
        qty_delta = qty_current_eff - qty_prior_eff
        value_delta = value_current - value_prior
        # A prior position that's a near-zero residual (e.g. 0.000001 shares
        # left over from a rounding artifact) turned into a real position
        # produces a meaningless multi-million-percent change — null it out
        # rather than let it blow up the column (confirmed against real data:
        # this happens for a handful of funds every month).
        if qty_prior_eff and abs(qty_prior_eff) > Decimal("0.01"):
            raw_pct = qty_delta / qty_prior_eff * 100
            pct_delta = float(raw_pct) if abs(raw_pct) < Decimal("9999999999") else None
        else:
            pct_delta = None

        movement_rows.append(
            {
                "fund_id": r["fund_id"],
                "asset_id": r["asset_id"],
                "ref_date": ref_date,
                "prior_ref_date": r["prior_ref_date"],
                "classification": classification,
                "qty_current": qty_current_eff,
                "qty_prior": qty_prior_eff,
                "value_current": value_current,
                "value_prior": value_prior,
                "qty_delta": qty_delta,
                "value_delta": value_delta,
                "pct_delta": pct_delta,
                "computed_at": datetime.utcnow(),
            }
        )

    if not movement_rows:
        return 0

    stmt = pg_insert(FundAssetMovement).values(movement_rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_movements_fund_asset_month",
        set_={
            "prior_ref_date": stmt.excluded.prior_ref_date,
            "classification": stmt.excluded.classification,
            "qty_current": stmt.excluded.qty_current,
            "qty_prior": stmt.excluded.qty_prior,
            "value_current": stmt.excluded.value_current,
            "value_prior": stmt.excluded.value_prior,
            "qty_delta": stmt.excluded.qty_delta,
            "value_delta": stmt.excluded.value_delta,
            "pct_delta": stmt.excluded.pct_delta,
            "computed_at": stmt.excluded.computed_at,
        },
    )
    try:
        db.execute(stmt)
        db.commit()
    except Exception:
        # Defense in depth, matching ingest_month's pattern — a failed statement
        # here must not leave the session's transaction in an aborted state for
        # whatever runs next in the same process (e.g. the next month in a
        # backfill loop, or the next scheduled job).
        db.rollback()
        logger.exception("movements %s: falhou", ref_date)
        raise
    logger.info("movements %s: %d linhas classificadas", ref_date, len(movement_rows))
    return len(movement_rows)
