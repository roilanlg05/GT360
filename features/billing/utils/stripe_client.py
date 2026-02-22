"""
Stripe client helpers.

All calls to the Stripe API go through this module.
"""
import stripe
import logging
from shared.settings import settings

logger = logging.getLogger(__name__)

# Configure Stripe once at module import
stripe.api_key = settings.STRIPE_SECRET_KEY

_PRICE_MAP = {
    "Basic": settings.STRIPE_BASIC_PRICE_ID,
    "Pro": settings.STRIPE_PRO_PRICE_ID,
}


def get_price_id(plan: str) -> str:
    price_id = _PRICE_MAP.get(plan)
    if not price_id:
        raise ValueError(f"No Stripe price configured for plan '{plan}'")
    return price_id


def get_or_create_customer(org_id: str, org_name: str, manager_email: str) -> str:
    """
    Return an existing Stripe Customer ID or create one.
    Uses org_id as metadata for idempotent lookup.
    """
    existing = stripe.Customer.search(
        query=f'metadata["organization_id"]:"{org_id}"',
        limit=1
    )
    if existing.data:
        return existing.data[0].id

    customer = stripe.Customer.create(
        email=manager_email,
        name=org_name,
        metadata={"organization_id": org_id}
    )
    return customer.id


def create_checkout_session(
    customer_id: str,
    price_id: str,
    org_id: str,
    success_url: str,
    cancel_url: str,
) -> stripe.checkout.Session:
    return stripe.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"organization_id": org_id},
        allow_promotion_codes=True,
    )


def create_portal_session(customer_id: str, return_url: str) -> stripe.billing_portal.Session:
    return stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url,
    )


def verify_webhook(payload: bytes, sig_header: str) -> stripe.Event:
    return stripe.Webhook.construct_event(
        payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
    )
