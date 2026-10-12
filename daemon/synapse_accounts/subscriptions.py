"""Account-bound plan foundation. No client-side paid-plan self-assignment."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import DateTime, ForeignKey, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .db import Account, Base

PLAN_KEYS = ("free", "plus", "pro", "unlimited")
# Limits/prices are deliberately unset until the product decisions are final.
PLAN_CATALOG = {
    key: {"id": key, "name": key.title(), "available_for_purchase": False, "price": None}
    for key in PLAN_KEYS
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


def get_account_plan(db: Session, account: Account) -> dict[str, Any]:
    row = db.scalar(select(AccountPlan).where(AccountPlan.account_id == account.id))
    # Existing and new accounts remain Free until a trusted billing integration grants a tier.
    plan = row.plan_id if row and row.plan_id in PLAN_KEYS else "free"
    if plan != "free" and (row is None or row.billing_status not in ("active", "trialing")):
        plan = "free"
    return {
        "account_id": account.id,
        "plan": plan,
        "billing_status": row.billing_status if row else "inactive",
        "features": {"account_sync": True, "device_inventory": True},
        "limits": {},
        "billing_configured": False,
    }


def install_subscription_routes(app, current_account, get_db) -> None:
    router = APIRouter(prefix="/v1")
    @router.get("/plans")
    def list_plans() -> dict[str, Any]:
        return {"plans": list(PLAN_CATALOG.values()), "paid_checkout_enabled": False}

    @router.get("/subscription")
    def subscription(account: Account = Depends(current_account),
                     db: Session = Depends(get_db)) -> dict[str, Any]:
        return get_account_plan(db, account)

    app.include_router(router)
