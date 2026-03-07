"""
Stripe webhook handler.

Endpoint: POST /v1/webhooks/stripe  (public — verified via Stripe signature)

Events handled:
  - checkout.session.completed       → link subscription to org, mark active
  - customer.subscription.updated    → sync plan / status / period
  - customer.subscription.deleted    → mark canceled
  - invoice.paid                     → update current period dates
  - invoice.payment_failed           → notify managers via WS, mark past_due
"""
import json
import logging
from datetime import datetime, timezone

import stripe
from fastapi import APIRouter, HTTPException, Request
from psqlmodel import Select, AsyncSession

from shared.db.db_config import get_db
from shared.db.schemas import Subscription
from shared.db.schemas.billing.subscriptions import SubscriptionStatus, PlanType
from shared.settings import settings
from features.trips.utils.org_ws_manager import org_manager
from shared.redis.redis_client import redis_client as redis

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Webhooks"])


# Map Stripe plan metadata / product names → internal plan type
_STRIPE_STATUS_MAP = {
    "trialing": SubscriptionStatus.TRIALING,
    "active": SubscriptionStatus.ACTIVE,
    "past_due": SubscriptionStatus.PAST_DUE,
    "canceled": SubscriptionStatus.CANCELED,
    "unpaid": SubscriptionStatus.UNPAID,
    "incomplete": SubscriptionStatus.PAST_DUE,
    "incomplete_expired": SubscriptionStatus.CANCELED,
    "paused": SubscriptionStatus.CANCELED,
}


def _plan_from_price_id(price_id: str) -> str | None:
    if price_id == settings.STRIPE_BASIC_PRICE_ID:
        return PlanType.BASIC
    if price_id == settings.STRIPE_PRO_PRICE_ID:
        return PlanType.PRO
    return None


def _ts(unix: int | None) -> datetime | None:
    if unix is None:
        return None
    return datetime.fromtimestamp(unix, tz=timezone.utc)


async def _get_sub_by_org(session: AsyncSession, org_id: str) -> Subscription | None:
    return await session.exec(
        Select(Subscription).Where(Subscription.organization_id == org_id)
    ).first()


async def _get_sub_by_stripe_id(session: AsyncSession, stripe_sub_id: str) -> Subscription | None:
    return await session.exec(
        Select(Subscription).Where(Subscription.stripe_subscription_id == stripe_sub_id)
    ).first()


async def _notify_managers(org_id: str, payload: dict) -> None:
    """Publish a billing event to the org Redis channel so all workers reach connected managers."""
    try:
        channel = f"org:{org_id}"
        await redis.publish(channel, json.dumps(payload))
    except Exception as e:
        logger.warning(f"[BILLING_WS] Failed to publish billing event for org {org_id}: {e}")


# ─── Event Handlers ───────────────────────────────────────────────────────────

async def _handle_checkout_completed(event: stripe.Event, session: AsyncSession) -> None:
    cs = event["data"]["object"]
    org_id = cs.get("metadata", {}).get("organization_id")
    stripe_customer_id = cs.get("customer")
    stripe_sub_id = cs.get("subscription")

    if not org_id or not stripe_sub_id:
        logger.warning("[BILLING] checkout.session.completed missing org_id or subscription")
        return

    # Retrieve full subscription object from Stripe to get price info
    stripe_sub = stripe.Subscription.retrieve(stripe_sub_id)
    price_id = stripe_sub["items"]["data"][0]["price"]["id"] if stripe_sub["items"]["data"] else None
    plan_type = _plan_from_price_id(price_id) if price_id else None
    status = _STRIPE_STATUS_MAP.get(stripe_sub["status"], SubscriptionStatus.ACTIVE)

    sub = await _get_sub_by_org(session, org_id)
    if not sub:
        logger.error(f"[BILLING] No subscription record for org {org_id}")
        return

    sub.stripe_customer_id = stripe_customer_id
    sub.stripe_subscription_id = stripe_sub_id
    sub.plan_type = plan_type
    sub.status = status
    sub.current_period_start = _ts(stripe_sub.get("current_period_start"))
    sub.current_period_end = _ts(stripe_sub.get("current_period_end"))
    sub.cancel_at_period_end = stripe_sub.get("cancel_at_period_end", False)
    sub.updated_at = datetime.now(timezone.utc)

    session.add(sub)
    await session.commit()
    print(
        f"[BILLING] checkout.session.completed | org={org_id} plan={plan_type} "
        f"status={status} period={sub.current_period_start} → {sub.current_period_end}"
    )


async def _handle_subscription_updated(event: stripe.Event, session: AsyncSession) -> None:
    stripe_sub = event["data"]["object"]
    stripe_sub_id = stripe_sub["id"]
    org_id = stripe_sub.get("metadata", {}).get("organization_id")

    sub = await _get_sub_by_stripe_id(session, stripe_sub_id)
    if not sub and org_id:
        sub = await _get_sub_by_org(session, org_id)
    if not sub:
        logger.warning(f"[BILLING] subscription.updated: no local record for {stripe_sub_id}")
        return

    price_id = stripe_sub["items"]["data"][0]["price"]["id"] if stripe_sub["items"]["data"] else None
    plan_type = _plan_from_price_id(price_id) if price_id else sub.plan_type
    status = _STRIPE_STATUS_MAP.get(stripe_sub["status"], sub.status)

    sub.plan_type = plan_type
    sub.status = status
    # Only update period if Stripe actually provides them — never overwrite with None
    period_start = _ts(stripe_sub.get("current_period_start"))
    period_end = _ts(stripe_sub.get("current_period_end"))
    if period_start is not None:
        sub.current_period_start = period_start
    if period_end is not None:
        sub.current_period_end = period_end
    sub.cancel_at_period_end = stripe_sub.get("cancel_at_period_end", False)
    sub.updated_at = datetime.now(timezone.utc)

    session.add(sub)
    await session.commit()
    print(
        f"[BILLING] customer.subscription.updated | org={sub.organization_id} plan={plan_type} "
        f"status={status} period={period_start} → {period_end}"
    )


async def _handle_subscription_deleted(event: stripe.Event, session: AsyncSession) -> None:
    stripe_sub = event["data"]["object"]
    stripe_sub_id = stripe_sub["id"]

    sub = await _get_sub_by_stripe_id(session, stripe_sub_id)
    if not sub:
        logger.warning(f"[BILLING] subscription.deleted: no local record for {stripe_sub_id}")
        return

    sub.status = SubscriptionStatus.CANCELED
    sub.updated_at = datetime.now(timezone.utc)
    session.add(sub)
    await session.commit()

    org_id = str(sub.organization_id)
    await _notify_managers(org_id, {
        "type": "billing_event",
        "event": "subscription_canceled",
        "message": (
            "Your subscription has been canceled. "
            "You will lose access to paid features at the end of the current period."
        ),
        "subscription_status": SubscriptionStatus.CANCELED,
    })
    print(f"[BILLING] customer.subscription.deleted | org={org_id} → CANCELED")


async def _handle_invoice_paid(event: stripe.Event, session: AsyncSession) -> None:
    invoice = event["data"]["object"]
    stripe_sub_id = invoice.get("subscription")
    print(f"[BILLING] invoice.paid → stripe_sub_id={stripe_sub_id}")
    if not stripe_sub_id:
        print("[BILLING] invoice.paid → no stripe_sub_id, skipping")
        return

    sub = await _get_sub_by_stripe_id(session, stripe_sub_id)
    print(f"[BILLING] invoice.paid → local sub found: {sub is not None} | org={getattr(sub, 'organization_id', None)}")
    if not sub:
        return

    # If the subscription was past_due/unpaid, restore it to active
    if sub.status in (SubscriptionStatus.PAST_DUE, SubscriptionStatus.UNPAID):
        sub.status = SubscriptionStatus.ACTIVE
        org_id = str(sub.organization_id)
        await _notify_managers(org_id, {
            "type": "billing_event",
            "event": "payment_recovered",
            "message": "Payment received. Your subscription is now active again.",
            "subscription_status": SubscriptionStatus.ACTIVE,
        })

    # Prefer top-level period fields on the invoice (always present)
    period_start = _ts(invoice.get("period_start"))
    period_end = _ts(invoice.get("period_end"))

    # Fallback: scan line items for the subscription charge
    if not period_start or not period_end:
        for line in invoice.get("lines", {}).get("data", []):
            period = line.get("period", {})
            period_start = period_start or _ts(period.get("start"))
            period_end = period_end or _ts(period.get("end"))
            if period_start and period_end:
                break

    if period_start is not None:
        sub.current_period_start = period_start
    if period_end is not None:
        sub.current_period_end = period_end

    print(
        f"[BILLING] invoice.paid | org={sub.organization_id} "
        f"period={period_start} → {period_end}"
    )

    sub.updated_at = datetime.now(timezone.utc)
    session.add(sub)
    await session.commit()


async def _handle_payment_failed(event: stripe.Event, session: AsyncSession) -> None:
    invoice = event["data"]["object"]
    stripe_sub_id = invoice.get("subscription")
    if not stripe_sub_id:
        return

    sub = await _get_sub_by_stripe_id(session, stripe_sub_id)
    if not sub:
        return

    sub.status = SubscriptionStatus.PAST_DUE
    sub.updated_at = datetime.now(timezone.utc)
    session.add(sub)
    await session.commit()

    org_id = str(sub.organization_id)
    attempt_count = invoice.get("attempt_count", 1)
    next_attempt = invoice.get("next_payment_attempt")
    next_attempt_str = (
        datetime.fromtimestamp(next_attempt, tz=timezone.utc).strftime("%B %d, %Y")
        if next_attempt else "soon"
    )

    await _notify_managers(org_id, {
        "type": "billing_event",
        "event": "payment_failed",
        "message": (
            f"Payment failed (attempt {attempt_count}). "
            f"We will retry {next_attempt_str}. "
            "Please update your payment method to avoid service interruption."
        ),
        "subscription_status": SubscriptionStatus.PAST_DUE,
        "attempt_count": attempt_count,
    })
    print(f"[BILLING] invoice.payment_failed | org={org_id} attempt={attempt_count} next={next_attempt_str}")


# ─── Webhook Endpoint ─────────────────────────────────────────────────────────

@router.post("/v1/webhooks/stripe")
async def stripe_webhook(request: Request):
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Webhook not configured.")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError:
        logger.warning("[BILLING] Invalid Stripe webhook signature")
        raise HTTPException(status_code=400, detail="Invalid signature.")
    except Exception as e:
        logger.error(f"[BILLING] Webhook parse error: {e}")
        raise HTTPException(status_code=400, detail="Webhook parse error.")

    # Process event in a DB session
    from shared.db.db_config import engine
    from psqlmodel import AsyncSession as _AsyncSession

    async with _AsyncSession(engine) as session:
        try:
            print(f"[BILLING] Event received: {event['type']}")
            match event["type"]:
                case "checkout.session.completed":
                    await _handle_checkout_completed(event, session)
                case "customer.subscription.updated":
                    await _handle_subscription_updated(event, session)
                case "customer.subscription.deleted":
                    await _handle_subscription_deleted(event, session)
                case "invoice.paid":
                    await _handle_invoice_paid(event, session)
                case "invoice.payment_failed":
                    await _handle_payment_failed(event, session)
                case _:
                    print(f"[BILLING] Unhandled event (ignored): {event['type']}")
        except Exception as e:
            print(f"[BILLING] ERROR processing {event['type']}: {e}")
            # Return 200 anyway to prevent Stripe retries for non-transient errors
            return {"received": True, "error": str(e)}

    return {"received": True}
