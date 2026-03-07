from fastapi import APIRouter, HTTPException, Depends, Request, Header
from fastapi.responses import JSONResponse
from psqlmodel import Select, AsyncSession
from shared.db.db_config import get_db
from shared.db.schemas import Subscription, Organization, Manager, User
from shared.db.schemas.billing.subscriptions import SubscriptionStatus, PlanType
from shared.settings import settings
from features.auth.utils import verify_role
from features.billing.models.billing_models import CheckoutRequest, ActivateEnterpriseRequest
from features.billing.utils.stripe_client import (
    get_or_create_customer,
    create_checkout_session,
    create_portal_session,
    get_price_id,
)
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/billing", tags=["Billing"])
admin_router = APIRouter(prefix="/v1/admin/billing", tags=["Admin - Billing"])


# ─── Manager Endpoints ──────────────────────────────────────────────────────

@router.get("/subscription")
async def get_subscription_status(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
):
    """Return current subscription info for the manager's organization."""
    org_id = request.state.user_data.get("organization_id")

    sub = await session.exec(
        Select(Subscription).Where(Subscription.organization_id == org_id)
    ).first()

    if not sub:
        # Org registered before billing was introduced — backfill a trial subscription
        from shared.db.schemas.billing.subscriptions import PlanType
        from datetime import timedelta
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

    now_utc = datetime.now(timezone.utc)
    trial_end = sub.trial_end
    if trial_end and trial_end.tzinfo is None:
        trial_end = trial_end.replace(tzinfo=timezone.utc)

    # If trialing but expired, reflect that in the response
    effective_status = sub.status
    if sub.status == SubscriptionStatus.TRIALING and trial_end and now_utc > trial_end:
        effective_status = "trial_expired"

    return {
        "status": effective_status,
        "plan_type": sub.plan_type,
        "trial_start": sub.trial_start.isoformat() if sub.trial_start else None,
        "trial_end": trial_end.isoformat() if trial_end else None,
        "current_period_start": sub.current_period_start.isoformat() if sub.current_period_start else None,
        "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
        "cancel_at_period_end": sub.cancel_at_period_end,
        "has_payment_method": sub.stripe_customer_id is not None,
    }


@router.post("/checkout")
async def create_checkout(
    body: CheckoutRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
):
    """
    Create a Stripe Checkout Session for the given plan.
    Returns a checkout_url the frontend should redirect to.
    """
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Payment system not configured.")

    if body.plan not in (PlanType.BASIC, PlanType.PRO):
        raise HTTPException(
            status_code=400,
            detail="Invalid plan. Choose 'Basic' or 'Pro'. For Enterprise, contact us."
        )

    user_data = request.state.user_data
    org_id = user_data.get("organization_id")
    manager_email = user_data.get("email", "")
    user_id = user_data.get("id")

    # Fetch org name for Stripe customer
    org = await session.exec(
        Select(Organization).Where(Organization.id == org_id)
    ).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")

    sub = await session.exec(
        Select(Subscription).Where(Subscription.organization_id == org_id)
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="No subscription record found.")

    if sub.status == SubscriptionStatus.ACTIVE:
        raise HTTPException(
            status_code=409,
            detail="You already have an active subscription. Use the billing portal to change your plan."
        )

    try:
        price_id = get_price_id(body.plan)
        customer_id = get_or_create_customer(str(org_id), org.name, manager_email)

        # Persist customer ID if not stored yet
        if not sub.stripe_customer_id:
            sub.stripe_customer_id = customer_id
            sub.updated_at = datetime.now(timezone.utc)
            session.add(sub)
            await session.commit()

        session_obj = create_checkout_session(
            customer_id=customer_id,
            price_id=price_id,
            org_id=str(org_id),
            success_url=f"{settings.BASE_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{settings.BASE_URL}/billing/plans",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[BILLING] Stripe error creating checkout: {e}")
        raise HTTPException(status_code=502, detail="Error communicating with payment provider.")

    return {"checkout_url": session_obj.url}


@router.post("/portal")
async def create_billing_portal(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
):
    """
    Generate a Stripe Customer Portal link for the manager to manage their subscription
    (update payment method, cancel, view invoices, etc.).
    """
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Payment system not configured.")

    org_id = request.state.user_data.get("organization_id")

    sub = await session.exec(
        Select(Subscription).Where(Subscription.organization_id == org_id)
    ).first()

    if not sub or not sub.stripe_customer_id:
        raise HTTPException(
            status_code=404,
            detail="No billing account found. Complete a checkout first."
        )

    try:
        portal = create_portal_session(
            customer_id=sub.stripe_customer_id,
            return_url=f"{settings.BASE_URL}/billing",
        )
    except Exception as e:
        logger.error(f"[BILLING] Stripe error creating portal: {e}")
        raise HTTPException(status_code=502, detail="Error communicating with payment provider.")

    return {"portal_url": portal.url}


@router.post("/enterprise/contact")
async def request_enterprise(
    request: Request,
    _role=Depends(verify_role(["manager"]))
):
    """
    Record manager's interest in Enterprise plan.
    The GT360 team will reach out manually.
    """
    user_data = request.state.user_data
    org_id = user_data.get("organization_id")
    email = user_data.get("email")

    logger.info(f"[BILLING] Enterprise contact request - org_id={org_id} email={email}")

    return {
        "message": "Thank you! Our team will contact you within 24 hours to discuss the Enterprise plan."
    }


# ─── Admin Endpoints ─────────────────────────────────────────────────────────

def _verify_admin(x_admin_key: str = Header(default="")):
    if not settings.ADMIN_SECRET_KEY or x_admin_key != settings.ADMIN_SECRET_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")


@admin_router.post("/activate-enterprise")
async def activate_enterprise(
    body: ActivateEnterpriseRequest,
    session: AsyncSession = Depends(get_db),
    _admin=Depends(_verify_admin),
):
    """
    Manually activate an Enterprise subscription for an organization.
    Requires X-Admin-Key header.
    """
    from uuid import UUID
    try:
        org_uuid = UUID(body.organization_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid organization_id format.")

    sub = await session.exec(
        Select(Subscription).Where(Subscription.organization_id == org_uuid)
    ).first()

    if not sub:
        raise HTTPException(status_code=404, detail="No subscription record found for this organization.")

    sub.plan_type = PlanType.ENTERPRISE
    sub.status = SubscriptionStatus.ACTIVE
    sub.updated_at = datetime.now(timezone.utc)
    session.add(sub)
    await session.commit()

    logger.info(f"[BILLING] Enterprise manually activated for org {body.organization_id}")

    return {
        "message": f"Enterprise plan activated for organization {body.organization_id}.",
        "note": body.note
    }
