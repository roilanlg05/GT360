# GT360 — Billing & Subscription — Frontend Integration Guide

> **Audience:** Frontend developers integrating the payment and subscription system.
> **Base URL:** `https://api.gt360.app`
> **Auth:** All billing endpoints require a valid `Authorization: Bearer <access_token>` header and the user must have the `manager` role. The only exception is the Stripe webhook (backend-to-backend only, never call this from frontend).

---

## Table of Contents

1. [Plan Overview](#1-plan-overview)
2. [Subscription Status Object](#2-subscription-status-object)
3. [Status & Access Matrix](#3-status--access-matrix)
4. [Core Flows](#4-core-flows)
   - [4.1 Check subscription on app load](#41-check-subscription-on-app-load)
   - [4.2 Subscribe (Stripe Checkout)](#42-subscribe-stripe-checkout)
   - [4.3 Manage subscription (Stripe Portal)](#43-manage-subscription-stripe-portal)
   - [4.4 Request Enterprise](#44-request-enterprise)
5. [Gating UI — What to Block](#5-gating-ui--what-to-block)
6. [API Error Codes](#6-api-error-codes)
7. [WebSocket Billing Events](#7-websocket-billing-events)
8. [Suggested Frontend State](#8-suggested-frontend-state)
9. [Page / Route Map](#9-page--route-map)

---

## 1. Plan Overview

| Plan | Price | Locations | Drivers | Schedule upload |
|------|-------|-----------|---------|-----------------|
| **Trial** | Free (30 days) | 1 | ✅ | ✅ |
| **Basic** | $99/mo | 1 | ✅ | ✅ |
| **Pro** | $249.99/mo | 3 | ✅ | ✅ |
| **Enterprise** | Contact us | Unlimited | ✅ | ✅ |

- The trial starts **automatically** the moment the manager registers.
- Without an active subscription (or with an expired trial) the manager can **only edit their profile**. Everything else is blocked.

---

## 2. Subscription Status Object

```
GET /v1/billing/subscription
Authorization: Bearer <token>
```

### Response `200`

```jsonc
{
  "status": "trialing",          // See status values below
  "plan_type": null,             // null during trial | "Basic" | "Pro" | "Enterprise"
  "trial_start": "2026-02-01T00:00:00+00:00",
  "trial_end":   "2026-03-03T00:00:00+00:00",
  "current_period_start": null,  // Populated after first payment
  "current_period_end":   null,
  "cancel_at_period_end": false, // true = will cancel at period end
  "has_payment_method": false    // true = Stripe customer exists
}
```

### `status` values

| Value | Meaning |
|-------|---------|
| `trialing` | Free trial is active |
| `trial_expired` | Trial ended, no paid subscription |
| `active` | Paid subscription is current |
| `past_due` | Payment failed, grace period active |
| `canceled` | Subscription was canceled |
| `unpaid` | Repeated failures, access suspended |

> **Tip:** Poll or cache this on app load. Re-fetch after returning from Stripe Checkout/Portal.

---

## 3. Status & Access Matrix

| Status | Upload schedule | Add location | Add driver | Profile | Billing page |
|--------|:-:|:-:|:-:|:-:|:-:|
| `trialing` (valid, < 1 location) | ✅ | ✅ | ✅ | ✅ | ✅ |
| `trialing` (valid, at limit) | ✅ (same location) | ❌ | ✅ | ✅ | ✅ |
| `trial_expired` | ❌ | ❌ | ❌ | ✅ | ✅ |
| `active` — Basic (< 1 location) | ✅ | ✅ | ✅ | ✅ | ✅ |
| `active` — Basic (at limit) | ✅ (same location) | ❌ | ✅ | ✅ | ✅ |
| `active` — Pro (< 3 locations) | ✅ | ✅ | ✅ | ✅ | ✅ |
| `active` — Enterprise | ✅ | ✅ | ✅ | ✅ | ✅ |
| `past_due` | ✅ (grace) | depends | ✅ | ✅ | ✅ |
| `canceled` / `unpaid` | ❌ | ❌ | ❌ | ✅ | ✅ |

> When the backend blocks an action it always returns `402` or `403` — see [Section 6](#6-api-error-codes).

---

## 4. Core Flows

### 4.1 Check subscription on app load

Run this once after the manager logs in (or on every page refresh). Store the result in global state.

```ts
async function loadSubscription(): Promise<Subscription> {
  const res = await api.get('/v1/billing/subscription');
  return res.data;
}
```

Use the result to:
- Show a trial countdown banner
- Show upgrade prompts
- Disable navigation items (drivers, schedule, locations) when access is blocked

---

### 4.2 Subscribe (Stripe Checkout)

The entire payment UI is hosted by Stripe — you just redirect the user.

```
POST /v1/billing/checkout
Authorization: Bearer <token>
Content-Type: application/json

{ "plan": "Basic" }   // or "Pro"
```

**Response `200`**
```json
{ "checkout_url": "https://checkout.stripe.com/c/pay/cs_live_..." }
```

**Integration steps:**

```ts
async function subscribe(plan: 'Basic' | 'Pro') {
  const { data } = await api.post('/v1/billing/checkout', { plan });
  // Redirect to Stripe — user pays there
  window.location.href = data.checkout_url;
}
```

After the user completes payment, Stripe redirects to:
- **Success:** `https://gt360.app/billing/success?session_id=cs_...`
- **Cancel:** `https://gt360.app/billing/plans`

**On the `/billing/success` page:**

```ts
// Re-fetch subscription to get updated status — webhook may take a few seconds
// Poll with backoff until status === "active"
async function pollUntilActive(maxAttempts = 8, delayMs = 1500) {
  for (let i = 0; i < maxAttempts; i++) {
    const sub = await loadSubscription();
    if (sub.status === 'active') return sub;
    await sleep(delayMs * (i + 1)); // exponential-ish backoff
  }
}
```

> The status is updated by the Stripe webhook — it arrives in ~1–3 seconds after payment. Do not rely on the `session_id` from the URL to confirm payment; always re-check `/v1/billing/subscription`.

**Possible errors from `POST /v1/billing/checkout`:**

| Status | `detail` | What to show |
|--------|----------|--------------|
| `400` | `"Invalid plan..."` | Dev error — check plan name |
| `409` | `"You already have an active subscription..."` | Redirect to Stripe Portal instead |
| `502` | `"Error communicating with payment provider."` | "Payment service unavailable, try again later" |

---

### 4.3 Manage subscription (Stripe Portal)

Let the manager update their payment method, download invoices, cancel, or change plans — all inside Stripe's hosted portal.

```
POST /v1/billing/portal
Authorization: Bearer <token>
```

**Response `200`**
```json
{ "portal_url": "https://billing.stripe.com/session/..." }
```

```ts
async function openBillingPortal() {
  const { data } = await api.post('/v1/billing/portal');
  window.location.href = data.portal_url;
}
```

Stripe will redirect the user back to `https://gt360.app/billing` when they exit the portal.

After returning, re-fetch `/v1/billing/subscription` to reflect any changes (cancellation, plan change, etc.).

**Possible errors:**

| Status | Meaning | What to show |
|--------|---------|--------------|
| `404` | No Stripe customer yet | "Please complete a checkout first" |
| `502` | Stripe unavailable | "Try again later" |

---

### 4.4 Request Enterprise

No self-service checkout for Enterprise — the GT360 team contacts them manually.

```
POST /v1/billing/enterprise/contact
Authorization: Bearer <token>
```

**Response `200`**
```json
{ "message": "Thank you! Our team will contact you within 24 hours..." }
```

```ts
async function requestEnterprise() {
  const { data } = await api.post('/v1/billing/enterprise/contact');
  showToast(data.message);
}
```

Show a confirmation message and disable the button after the request is sent.

---

## 5. Gating UI — What to Block

The backend enforces every restriction, but block the UI proactively for a smooth UX.

### Helper — derive access from subscription

```ts
type PlanType = 'Basic' | 'Pro' | 'Enterprise' | null;
type SubStatus = 'trialing' | 'trial_expired' | 'active' | 'past_due' | 'canceled' | 'unpaid';

interface Subscription {
  status: SubStatus;
  plan_type: PlanType;
  trial_end: string | null;
  cancel_at_period_end: boolean;
  has_payment_method: boolean;
}

function getAccess(sub: Subscription) {
  const effectivePlan: PlanType =
    sub.status === 'trialing' ? 'Basic' : sub.plan_type;

  const canAccess =
    sub.status === 'trialing' || sub.status === 'active' || sub.status === 'past_due';

  return {
    canAddLocation: canAccess && (
      effectivePlan === 'Enterprise' ? true :
      effectivePlan === 'Pro'        ? locationCount < 3 :
                                       locationCount < 1   // Basic or trial
    ),
    canAddDriver:   canAccess,
    canUpload:      canAccess,
    needsUpgrade:   sub.status === 'trial_expired' || sub.status === 'canceled' || sub.status === 'unpaid',
    isTrialing:     sub.status === 'trialing',
    isPastDue:      sub.status === 'past_due',
    willCancel:     sub.cancel_at_period_end,
  };
}
```

### Trial banner

Show this on every page while `status === "trialing"`:

```ts
function getTrialDaysLeft(trialEnd: string): number {
  const ms = new Date(trialEnd).getTime() - Date.now();
  return Math.max(0, Math.ceil(ms / 86_400_000));
}
```

```
⏳ Your free trial ends in {N} days. Subscribe to keep full access.  [Choose a plan →]
```

Show urgency styling when `N <= 5`.

### Expired / no subscription wall

When `status === "trial_expired" | "canceled" | "unpaid"`, show a full-page or modal wall instead of the blocked content:

```
🔒 Your access has expired.
To continue using GT360, please activate a subscription.

[View Plans]
```

### Past-due banner

When `status === "past_due"`:

```
⚠️ Your last payment failed. Update your payment method to avoid losing access.  [Update now →]
```

`[Update now →]` calls `POST /v1/billing/portal`.

### Will-cancel notice

When `cancel_at_period_end === true`:

```
ℹ️ Your subscription is set to cancel on {current_period_end}. Renew anytime.  [Renew →]
```

---

## 6. API Error Codes

When the backend blocks a restricted action, it returns one of these:

| HTTP | When | Suggested UI response |
|------|------|----------------------|
| `402` | No subscription / trial expired / status not active | Show subscription wall or redirect to `/billing/plans` |
| `403` | Subscription active but plan limit reached (e.g. adding 2nd location on Basic) | Show upgrade prompt: "Upgrade to Pro to add more locations" |
| `409` | Already has active subscription and tries to checkout again | Redirect to `/billing/portal` |

**Example interceptor (axios):**

```ts
api.interceptors.response.use(
  res => res,
  err => {
    const status = err.response?.status;
    const detail = err.response?.data?.detail ?? '';

    if (status === 402) {
      // Subscription required
      router.push('/billing/plans');
    } else if (status === 403 && detail.includes('plan allows')) {
      // Plan limit — show upgrade modal
      showUpgradeModal(detail);
    }

    return Promise.reject(err);
  }
);
```

---

## 7. WebSocket Billing Events

Billing alerts are pushed to managers in real time via the **existing org WebSocket** — no separate connection is needed.

### Connection

```
WS wss://api.gt360.app/ws/org?organization_id={org_id}&token={access_token}
```

> This is the same WebSocket used for org-level events (location_deleted, etc.). Billing events arrive on the same connection, **only for managers**.

### Billing event shape

```jsonc
{
  "type": "billing_event",
  "event": "payment_failed",          // See event types below
  "message": "Payment failed (attempt 1). We will retry March 5, 2026. Please update your payment method.",
  "subscription_status": "past_due",
  "attempt_count": 1                  // Only present on payment_failed
}
```

### Event types

| `event` | When | `subscription_status` | Recommended action |
|---------|------|-----------------------|-------------------|
| `payment_failed` | Invoice payment fails | `past_due` | Show persistent warning banner + link to Stripe Portal |
| `payment_recovered` | Invoice paid after past_due | `active` | Dismiss warning banner, show success toast |
| `subscription_canceled` | Subscription deleted in Stripe | `canceled` | Show cancellation notice, redirect to billing page |

### Handler example

```ts
ws.addEventListener('message', (evt) => {
  const msg = JSON.parse(evt.data);

  if (msg.type !== 'billing_event') return;

  // Update local subscription state
  setSubscription(prev => ({ ...prev, status: msg.subscription_status }));

  switch (msg.event) {
    case 'payment_failed':
      showBanner({
        type: 'error',
        text: msg.message,
        action: { label: 'Update payment method', onClick: openBillingPortal },
        persistent: true,
      });
      break;

    case 'payment_recovered':
      dismissBanner('payment_failed');
      showToast('Payment successful — your subscription is active again.', 'success');
      break;

    case 'subscription_canceled':
      showBanner({
        type: 'warning',
        text: msg.message,
        action: { label: 'Resubscribe', onClick: () => router.push('/billing/plans') },
        persistent: true,
      });
      break;
  }
});
```

---

## 8. Suggested Frontend State

```ts
// Zustand / Redux slice example
interface BillingState {
  subscription: Subscription | null;
  loading: boolean;
  // Derived helpers (computed from subscription)
  access: ReturnType<typeof getAccess> | null;
}

// Load once at login, refresh after checkout/portal return
const useBillingStore = create<BillingState>((set) => ({
  subscription: null,
  loading: false,
  access: null,

  fetchSubscription: async () => {
    set({ loading: true });
    try {
      const sub = await loadSubscription();
      set({ subscription: sub, access: getAccess(sub), loading: false });
    } catch {
      set({ loading: false });
    }
  },
}));
```

---

## 9. Page / Route Map

| Route | Purpose | Who sees it |
|-------|---------|-------------|
| `/billing/plans` | Choose Basic / Pro / Enterprise | Any manager |
| `/billing/success` | Post-checkout confirmation; polls for `active` status | Manager returning from Stripe |
| `/billing` | Subscription overview: plan, dates, invoices link, cancel | Manager with active sub |

### `/billing/plans` — logic

```
1. Load subscription
2. if status === 'active' AND cancel_at_period_end === false
     → redirect to /billing (already subscribed)
3. Show plan cards: Basic / Pro / Enterprise
4. [Subscribe] → POST /v1/billing/checkout → redirect to checkout_url
5. [Contact us] (Enterprise) → POST /v1/billing/enterprise/contact
```

### `/billing` — logic

```
1. Load subscription
2. Show current plan, billing period, renewal date
3. [Manage subscription] → POST /v1/billing/portal → redirect to portal_url
4. If cancel_at_period_end → show "Cancels on {date}" notice
5. If past_due → show payment failure banner
```

---

## Quick Reference

```
GET  /v1/billing/subscription         → subscription status object
POST /v1/billing/checkout             → { plan: "Basic"|"Pro" }  →  { checkout_url }
POST /v1/billing/portal               → { portal_url }
POST /v1/billing/enterprise/contact   → { message }

WS   /ws/org?organization_id=&token=  → billing_event messages (managers only)
```
