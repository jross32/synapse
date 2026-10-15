"""Reviewed fixed-scope offers for Fast Money Client Ops.

Catalog data is not a checkout authorization or a promise of availability.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Offer:
    slug: str
    name: str
    setup_usd: Decimal
    deposit_usd: Decimal
    support_monthly_usd: Decimal
    estimated_business_days: tuple[int, int]
    deliverables: tuple[str, ...]
    exclusions: tuple[str, ...]
    requires_owner_approval: bool = True

    @property
    def acceptance_balance_usd(self) -> Decimal:
        return self.setup_usd - self.deposit_usd

    def public_summary(self) -> dict:
        return {
            "slug": self.slug,
            "name": self.name,
            "setup_usd": str(self.setup_usd),
            "deposit_usd": str(self.deposit_usd),
            "acceptance_balance_usd": str(self.acceptance_balance_usd),
            "optional_support_monthly_usd": str(self.support_monthly_usd),
            "estimated_business_days": list(self.estimated_business_days),
            "deliverables": list(self.deliverables),
            "exclusions": list(self.exclusions),
            "draft_only": True,
            "requires_owner_approval": self.requires_owner_approval,
        }


STARTER = Offer(
    slug="client-follow-up-scheduling-starter",
    name="Client Follow-Up & Scheduling Starter",
    setup_usd=Decimal("1500.00"),
    deposit_usd=Decimal("750.00"),
    support_monthly_usd=Decimal("200.00"),
    estimated_business_days=(7, 14),
    deliverables=(
        "One approved lead-intake source",
        "Operator lead dashboard and next-action status",
        "One appointment-request workflow",
        "Two approved follow-up templates with review/consent gates",
        "Operator handoff and written instructions",
        "Acceptance walkthrough using fictional test data",
    ),
    exclusions=(
        "Unapproved outbound messaging or unsolicited bulk email",
        "SMS/WhatsApp/telephony and third-party usage charges",
        "Unlimited integrations, custom native apps, and 24/7 support",
        "Guaranteed sales or revenue outcomes",
    ),
)

OFFERS = {STARTER.slug: STARTER}


def get_offer(slug: str) -> Offer:
    return OFFERS[slug]


def validate_catalog() -> None:
    for offer in OFFERS.values():
        assert offer.setup_usd > 0
        assert Decimal("0") < offer.deposit_usd <= offer.setup_usd
        assert offer.support_monthly_usd >= 0
        assert 0 < offer.estimated_business_days[0] <= offer.estimated_business_days[1]
        assert offer.deliverables and offer.exclusions
        assert offer.requires_owner_approval


validate_catalog()
