"""
Subscription guard utilities.

Use check_can_add_location() and check_can_add_driver() inside route handlers
to enforce plan limits before performing the restricted action.

For generic manager write endpoints use the FastAPI dependency:

    from features.billing.utils.subscription_guard import ActiveSubscription
    ...
    _sub=Depends(ActiveSubscription),
"""
from datetime import datetime, timezone
from fastapi import HTTPException, Depends, Request
from psqlmodel import Select, Count, AsyncSession

from shared.db.db_config import get_db
from shared.db.schemas.billing.subscriptions import Subscription, SubscriptionStatus, PlanType


def _ensure_utc(dt: datetime) -> datetime:
    """Return a timezone-aware UTC datetime, regardless of input."""
    if dt is None:
        return dt
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def get_subscription(session: AsyncSession, org_id: str) -> Subscription | None:
    return await session.exec(
        Select(Subscription).Where(Subscription.organization_id == org_id)
    ).first()


def _resolve_effective_plan(sub: Subscription) -> str | None:
    """
    Resolve the effective plan for restriction checks.

    Returns:
        plan string ("Basic", "Pro", "Enterprise") if access is allowed
        Raises HTTPException 402 if subscription does not grant access
    """
    now_utc = datetime.now(timezone.utc)

    if sub.status == SubscriptionStatus.TRIALING:
        trial_end = _ensure_utc(sub.trial_end)
        if now_utc > trial_end:
            raise HTTPException(
                status_code=402,
                detail="Your free trial has expired. Please subscribe to continue using GT360."
            )
        # During trial: Basic-level access
        return PlanType.BASIC

    if sub.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.PAST_DUE):
        return sub.plan_type

    raise HTTPException(
        status_code=402,
        detail=f"Your subscription is not active (status: {sub.status}). "
               "Please update your payment method or reactivate your subscription."
    )


async def _get_or_create_trial(session: AsyncSession, org_id: str) -> "Subscription":
    """Return subscription, auto-creating a trial for orgs that pre-date billing."""
    from datetime import timedelta
    from shared.settings import settings
    sub = await get_subscription(session, org_id)
    if not sub:
        now_utc = datetime.now(timezone.utc)
        sub = Subscription(
            organization_id=org_id,
            status=SubscriptionStatus.TRIALING,
            trial_start=now_utc,
            trial_end=now_utc + timedelta(days=settings.FREE_TRIAL_DAYS),
        )
        session.add(sub)
        await session.commit()
        await session.refresh(sub)
    return sub


async def check_can_add_location(session: AsyncSession, org_id: str) -> None:
    """
    Raise HTTP 402/403 if the org is not allowed to create a new location.
    Call this BEFORE creating the Location record.
    """
    from shared.db.schemas import Location

    sub = await _get_or_create_trial(session, org_id)

    effective_plan = _resolve_effective_plan(sub)

    # Enterprise: no location cap
    if effective_plan == PlanType.ENTERPRISE:
        return

    count_result = await session.exec(
        Select(Count(Location.id)).From(Location).Where(Location.organization_id == org_id)
    ).first()
    location_count = count_result[0] if count_result else 0

    limits = {PlanType.BASIC: 1, PlanType.PRO: 3}
    max_loc = limits.get(effective_plan, 1)

    if location_count >= max_loc:
        upgrades = {PlanType.BASIC: "Pro or Enterprise", PlanType.PRO: "Enterprise"}
        upgrade_to = upgrades.get(effective_plan, "a higher plan")
        raise HTTPException(
            status_code=403,
            detail=(
                f"Your {effective_plan} plan allows up to {max_loc} location(s). "
                f"You already have {location_count}. Upgrade to {upgrade_to} to add more."
            )
        )


async def check_can_add_driver(session: AsyncSession, org_id: str) -> None:
    """
    Raise HTTP 402 if the org is not allowed to create a new driver.
    Any active subscription (including valid trial) allows adding drivers.
    """
    sub = await _get_or_create_trial(session, org_id)
    # This will raise if trial expired or status is non-active
    _resolve_effective_plan(sub)


async def check_can_upload_schedule(session: AsyncSession, org_id: str) -> None:
    """
    Raise HTTP 402 if the org is not allowed to upload a trip schedule.
    Any active subscription (including valid trial) allows uploads.
    This check runs ALWAYS, regardless of whether a new location is created.
    """
    sub = await _get_or_create_trial(session, org_id)
    _resolve_effective_plan(sub)


async def ActiveSubscription(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> None:
    """
    FastAPI dependency — blocks any manager write operation when the
    subscription is expired or inactive.

    Usage:
        @router.post("/path")
        async def endpoint(..., _sub=Depends(ActiveSubscription)):
    """
    org_id = request.state.user_data.get("organization_id")
    if not org_id:
        raise HTTPException(status_code=403, detail="Organization not found in session.")
    sub = await _get_or_create_trial(session, str(org_id))
    _resolve_effective_plan(sub)
