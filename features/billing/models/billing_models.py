from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class CheckoutRequest(BaseModel):
    plan: str  # "Basic" | "Pro"


class SubscriptionResponse(BaseModel):
    status: str
    plan_type: Optional[str]
    trial_start: Optional[datetime]
    trial_end: Optional[datetime]
    current_period_start: Optional[datetime]
    current_period_end: Optional[datetime]
    cancel_at_period_end: bool
    stripe_subscription_id: Optional[str]
    has_payment_method: bool


class ActivateEnterpriseRequest(BaseModel):
    organization_id: str
    note: Optional[str] = None
