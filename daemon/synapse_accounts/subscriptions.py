"""Account-owned subscription entitlements and metering.

All paid changes are server-only; public endpoints cannot upgrade themselves.
Metering is opt-in until actual product limits and billing are approved.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from .db import Account, Base

PLAN_KEYS = ("free", "plus", "pro", "unlimited")
PLAN_CATALOG = {
    key: {"id": key, "name": key.title(), "available_for_purchase": False, "price": None}
    for key in PLAN_KEYS
}
# These are backend demonstration entitlements, NOT finalized commercial quotas.
# Nothing in the existing daemon is gated by these until explicit integration.
PLAN_RULES: dict[str, dict[str, int | None]] = {
    "free": {"preview_actions": 3},
    "plus": {"preview_actions": 30},
    "pro": {"preview_actions": 300},
    "unlimited": {"preview_actions": None},
}


class AccountPlan(Base):
    __tablename__ = "account_plans"
    account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True
    )
    plan_id: Mapped[str] = mapped_column(String(24), nullable=False, default="free")
    billing_status: Mapped[str] = mapped_column(String(24), nullable=False, default="inactive")
    billing_provider: Mapped[str | None] = mapped_column(String(24), nullable=True)
    provider_customer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider_subscription_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class UsageCounter(Base):
    __tablename__ = "subscription_usage_counters"
    __table_args__ = (UniqueConstraint("account_id", "metric", "period", name="uq_subscription_usage_counter"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(64), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    metric: Mapped[str] = mapped_column(String(64), nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class UsageEvent(Base):
    __tablename__ = "subscription_usage_events"
    __table_args__ = (UniqueConstraint("account_id", "event_key", name="uq_subscription_usage_event"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(64), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    event_key: Mapped[str] = mapped_column(String(128), nullable=False)
    metric: Mapped[str] = mapped_column(String(64), nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    units: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


def _period() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


def get_account_plan(db: Session, account: Account) -> dict[str, Any]:
    row = db.get(AccountPlan, account.id)
    plan = row.plan_id if row and row.plan_id in PLAN_KEYS else "free"
    if plan != "free" and (row is None or row.billing_status not in ("active", "trialing")):
        plan = "free"
    return {
        "account_id": account.id,
        "plan": plan,
        "billing_status": row.billing_status if row else "inactive",
        "features": {"account_sync": True, "device_inventory": True, "preview_actions": True},
        "limits": PLAN_RULES[plan].copy(),
        "billing_configured": False,
    }


def usage_snapshot(db: Session, account: Account) -> dict[str, Any]:
    plan = get_account_plan(db, account)
    period = _period()
    rows = db.scalars(select(UsageCounter).where(
        UsageCounter.account_id == account.id, UsageCounter.period == period
    )).all()
    used = {row.metric: row.used for row in rows}
    return {"account_id": account.id, "period": period, "metrics": {
        metric: {"used": used.get(metric, 0), "limit": limit,
                 "remaining": None if limit is None else max(0, limit - used.get(metric, 0))}
        for metric, limit in plan["limits"].items()
    }}


def consume_usage(db: Session, account: Account, *, metric: str, units: int, event_key: str) -> dict[str, Any]:
    if metric not in PLAN_RULES["free"]:
        raise HTTPException(422, "Unknown metered feature.")
    if units < 1 or units > 1000 or not event_key or len(event_key) > 128:
        raise HTTPException(422, "Invalid usage event.")
    existing = db.scalar(select(UsageEvent).where(
        UsageEvent.account_id == account.id, UsageEvent.event_key == event_key
    ))
    if existing is not None:
        if existing.metric != metric or existing.units != units:
            raise HTTPException(409, "Idempotency key already used for a different action.")
        return {"accepted": True, "duplicate": True, "usage": usage_snapshot(db, account)}
    period = _period()
    limit = get_account_plan(db, account)["limits"][metric]
    counter = db.scalar(select(UsageCounter).where(
        UsageCounter.account_id == account.id, UsageCounter.metric == metric, UsageCounter.period == period
    ))
    if counter is None:
        # Race-safe initial row creation: savepoint permits retry after unique conflict.
        try:
            with db.begin_nested():
                db.add(UsageCounter(id=str(uuid.uuid4()), account_id=account.id,
                                    metric=metric, period=period, used=0))
                db.flush()
        except IntegrityError:
            pass
    condition = [UsageCounter.account_id == account.id,
                 UsageCounter.metric == metric, UsageCounter.period == period]
    if limit is not None:
        condition.append(UsageCounter.used <= limit - units)
    result = db.execute(update(UsageCounter).where(*condition).values(
        used=UsageCounter.used + units
    ))
    if result.rowcount != 1:
        raise HTTPException(429, "Plan usage limit reached.")
    # The event and counter update commit in the same request transaction.
    # Unique index prevents duplicate events; duplicate concurrent requests may
    # receive a conflict and should retry with the same key.
    db.add(UsageEvent(id=str(uuid.uuid4()), account_id=account.id,
                      event_key=event_key, metric=metric, period=period, units=units))
    db.flush()
    return {"accepted": True, "duplicate": False, "usage": usage_snapshot(db, account)}


def set_plan_trusted(db: Session, *, account_id: str, plan_id: str,
                     billing_status: str, provider: str | None = None,
                     provider_subscription_id: str | None = None) -> None:
    """Internal trusted billing/admin entrypoint; never exposed as public plan mutation."""
    if plan_id not in PLAN_KEYS or billing_status not in (
        "inactive", "active", "trialing", "past_due", "canceled"
    ):
        raise ValueError("Invalid subscription state")
    if plan_id != "free" and billing_status in ("active", "trialing") and provider not in ("stripe", "admin"):
        raise ValueError("Paid grants require a trusted billing or admin source")
    if db.get(Account, account_id) is None:
        raise ValueError("Unknown account")
    row = db.get(AccountPlan, account_id)
    if row is None:
        row = AccountPlan(account_id=account_id)
        db.add(row)
    row.plan_id = plan_id
    row.billing_status = billing_status
    row.billing_provider = provider
    row.provider_subscription_id = provider_subscription_id
    row.updated_at = datetime.now(UTC)
    db.flush()


class PreviewUsageRequest(BaseModel):
    metric: str = Field(pattern="^preview_actions$")
    units: int = Field(ge=1, le=1000)
    event_key: str = Field(min_length=1, max_length=128)


def install_subscription_routes(app, current_account, get_db) -> None:
    router = APIRouter(prefix="/v1")

    @router.get("/plans")
    def list_plans() -> dict[str, Any]:
        return {"plans": list(PLAN_CATALOG.values()), "paid_checkout_enabled": False}

    @router.get("/subscription")
    def subscription(account: Account = Depends(current_account),
                     db: Session = Depends(get_db)) -> dict[str, Any]:
        return get_account_plan(db, account)

    @router.get("/subscription/usage")
    def usage(account: Account = Depends(current_account),
              db: Session = Depends(get_db)) -> dict[str, Any]:
        return usage_snapshot(db, account)

    # Explicit preview endpoint only: not wired to any existing paid product action.
    @router.post("/subscription/preview-usage")
    def preview_usage(payload: PreviewUsageRequest, account: Account = Depends(current_account),
                      db: Session = Depends(get_db)) -> dict[str, Any]:
        return consume_usage(db, account, metric=payload.metric, units=payload.units,
                             event_key=payload.event_key)

    app.include_router(router)
