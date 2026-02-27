# Driver Management API — Frontend Docs

Base URL: `/v1/organizations/{organization_id}/drivers`

All endpoints require **Manager** role. Send the access token in the `Authorization: Bearer <token>` header.

---

## 1. Resend Verification Email

Re-sends the account verification email to a driver that hasn't confirmed their email yet.

```
POST /v1/organizations/{organization_id}/drivers/{driver_id}/resend-verification
```

### Parameters

| Param             | In   | Type   | Required |
|-------------------|------|--------|----------|
| organization_id   | path | UUID   | yes      |
| driver_id         | path | UUID   | yes      |

### Request Body

None.

### Responses

**200 OK**
```json
{
  "message": "Verification email resent successfully"
}
```

**400 Bad Request** — driver already verified their email
```json
{
  "detail": "Email already verified"
}
```

**403 Forbidden** — manager doesn't belong to this org, or driver is from another org
```json
{
  "detail": "Not authorized for this organization"
}
```
```json
{
  "detail": "Driver does not belong to your organization"
}
```

**404 Not Found** — driver or user record doesn't exist
```json
{
  "detail": "Driver not found"
}
```

### Example (fetch)

```js
const res = await fetch(
  `${API_URL}/v1/organizations/${orgId}/drivers/${driverId}/resend-verification`,
  {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  }
);
```

### Notes
- Generates a new verification token valid for **24 hours**
- Invalidates any previous verification link
- The driver receives the same "Confirm Your Api360 Account" email

---

## 2. Delete Driver from Organization

Permanently removes a driver and their user account from the system.

```
DELETE /v1/organizations/{organization_id}/drivers/{driver_id}
```

### Parameters

| Param             | In   | Type   | Required |
|-------------------|------|--------|----------|
| organization_id   | path | UUID   | yes      |
| driver_id         | path | UUID   | yes      |

### Request Body

None.

### Responses

**200 OK**
```json
{
  "message": "Driver removed from organization successfully"
}
```

**403 Forbidden** — not authorized
```json
{
  "detail": "Not authorized for this organization"
}
```
```json
{
  "detail": "Driver does not belong to your organization"
}
```

**404 Not Found**
```json
{
  "detail": "Driver not found"
}
```

**409 Conflict** — driver has trips currently in progress
```json
{
  "detail": "Cannot delete driver with 2 active trip(s). Complete all trips first."
}
```

### Example (fetch)

```js
const res = await fetch(
  `${API_URL}/v1/organizations/${orgId}/drivers/${driverId}`,
  {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  }
);
```

### What gets deleted
| Data                  | Behavior                              |
|-----------------------|---------------------------------------|
| Driver record         | Deleted                               |
| User account          | Deleted                               |
| Shifts                | Deleted (cascade)                     |
| Expenses              | Deleted (cascade)                     |
| Tax information       | Deleted (cascade)                     |
| 1099 archive          | Deleted (cascade)                     |
| Trips                 | Preserved — driver field set to null  |
| Ratings               | Preserved — driver field set to null  |
| Reviews               | Preserved — driver field set to null  |

### Notes
- This action is **irreversible** — show a confirmation dialog before calling
- The driver's active sessions are immediately revoked
- Trips in `EN_ROUTE` status block deletion; the manager must wait for completion or reassign them first
