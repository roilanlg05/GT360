from psqlmodel import PSQLModel, table, Column
from psqlmodel.orm.types import timestamptz, uuid, varchar
from psqlmodel.utils import gen_default_uuid, now


class PlanType:
    BASIC = "Basic"
    PRO = "Pro"
    ENTERPRISE = "Enterprise"


class SubscriptionStatus:
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    UNPAID = "unpaid"


@table("subscriptions", schema="billing")
class Subscription(PSQLModel):

    id: uuid = Column(
        default=gen_default_uuid,
        primary_key=True
    )

    organization_id: uuid = Column(
        foreign_key="entities.organizations.id",
        on_delete="CASCADE",
        nullable=False,
        index=True,
        unique=True
    )

    # Stripe IDs (null until org subscribes)
    stripe_customer_id: str | None = Column(default=None, max_len=255, index=True)
    stripe_subscription_id: str | None = Column(default=None, max_len=255, index=True)

    # Plan: Basic | Pro | Enterprise (null during trial = Basic-level access)
    plan_type: str | None = Column(default=None, max_len=50, index=True)

    # Status: trialing | active | past_due | canceled | unpaid
    status: str = Column(
        max_len=50,
        default=SubscriptionStatus.TRIALING,
        nullable=False,
        index=True
    )

    # Free trial window (set at org creation)
    trial_start: timestamptz = Column(default=now, nullable=False)
    trial_end: timestamptz = Column(default=None, nullable=False)

    # Stripe billing period (populated after first payment)
    current_period_start: timestamptz = Column(default=None)
    current_period_end: timestamptz = Column(default=None)

    cancel_at_period_end: bool = Column(default=False, nullable=False)

    created_at: timestamptz = Column(default=now, nullable=False)
    updated_at: timestamptz = Column(default=now, nullable=False)
