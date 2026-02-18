# Driver Expenses Endpoint Guide

## Overview

The expense system allows drivers to submit expense reimbursement requests with receipt photos, and managers to review, approve, adjust, or reject them.

**Base URL:** `https://dev-api.gt360.app`

---

## 1. Submit Expense (Driver)

**`POST /v1/drivers/{driver_id}/expenses`**

Submits a new expense reimbursement request. Uses `multipart/form-data` because a receipt photo is required.

### Authentication
- **Role:** `driver`
- **Header:** `Authorization: Bearer <token>`

### Path Parameters

| Param | Type | Description |
|-------|------|-------------|
| `driver_id` | UUID | Driver's ID |

### Form Data

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `amount` | number | Yes | Expense amount in dollars (must be > 0) |
| `expense_type` | string | Yes | One of: `gas`, `maintenance`, `parking`, `tolls`, `car_wash`, `supplies`, `other` |
| `expense_date` | string | Yes | Date of expense (`YYYY-MM-DD`) |
| `description` | string | No | Optional description |
| `receipt_photo` | file | Yes | Receipt image (JPEG, PNG) or PDF. Max 10MB |

### Validations
- Amount must be greater than 0
- `expense_date` cannot be in the future
- `expense_date` cannot be more than 30 days old
- Receipt photo is required
- Allowed file types: `image/jpeg`, `image/png`, `application/pdf`
- Driver must exist and be active

### Success Response (200)

```json
{
  "status": "ok",
  "message": "Expense submitted for review",
  "expense": {
    "expense_id": "uuid",
    "driver_id": "uuid",
    "amount": 45.50,
    "expense_type": "gas",
    "description": "Fill up at Shell station",
    "expense_date": "2026-02-15",
    "receipt_photo_url": "/uploads/receipts/uuid.jpg",
    "receipt_uploaded": true,
    "status": "pending",
    "reviewed_at": null,
    "reviewed_by": null,
    "manager_notes": null,
    "rejection_reason": null,
    "pay_period_start": null,
    "pay_period_end": null,
    "included_in_payment": false,
    "created_at": "2026-02-15T10:30:00Z"
  }
}
```

### Error Responses

| Code | Detail |
|------|--------|
| 400 | `Invalid driver ID` |
| 400 | `Invalid date format. Use YYYY-MM-DD` |
| 400 | `Amount must be greater than 0` |
| 400 | `Expense date cannot be in the future` |
| 400 | `Expense date cannot be more than 30 days in the past` |
| 400 | `Invalid expense type` |
| 400 | `Invalid receipt file type` |
| 403 | `Driver is not active` |
| 404 | `Driver not found` |
| 413 | `Receipt file too large (max 10.0MB)` |

### Example (curl)

```bash
curl -X POST "https://dev-api.gt360.app/v1/drivers/{driver_id}/expenses" \
  -H "Authorization: Bearer <token>" \
  -F "amount=45.50" \
  -F "expense_type=gas" \
  -F "expense_date=2026-02-15" \
  -F "description=Fill up at Shell station" \
  -F "receipt_photo=@/path/to/receipt.jpg"
```

---

## 2. Get Driver Expenses (Driver)

**`GET /v1/drivers/{driver_id}/expenses`**

Returns paginated list of expenses for a driver with summary totals.

### Authentication
- **Role:** `driver`
- **Header:** `Authorization: Bearer <token>`

### Path Parameters

| Param | Type | Description |
|-------|------|-------------|
| `driver_id` | UUID | Driver's ID |

### Query Parameters

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `status` | string | all | Filter: `pending`, `verified`, `rejected`, `all` |
| `start_date` | string | - | Filter from date (`YYYY-MM-DD`) |
| `end_date` | string | - | Filter to date (`YYYY-MM-DD`) |
| `expense_type` | string | - | Filter by type (`gas`, `maintenance`, etc.) |
| `page` | int | 1 | Page number |
| `page_size` | int | 20 | Items per page |

### Success Response (200)

```json
{
  "expenses": [
    {
      "expense_id": "uuid",
      "driver_id": "uuid",
      "amount": 45.50,
      "expense_type": "gas",
      "description": "Fill up at Shell station",
      "expense_date": "2026-02-15",
      "receipt_photo_url": "/uploads/receipts/uuid.jpg",
      "receipt_uploaded": true,
      "status": "pending",
      "reviewed_at": null,
      "reviewed_by": null,
      "manager_notes": null,
      "rejection_reason": null,
      "pay_period_start": null,
      "pay_period_end": null,
      "included_in_payment": false,
      "created_at": "2026-02-15T10:30:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total_expenses": 5,
    "total_pages": 1
  },
  "summary": {
    "pending_count": 2,
    "pending_total": 95.50,
    "verified_count": 2,
    "verified_total": 120.00,
    "rejected_count": 1,
    "rejected_total": 30.00
  }
}
```

### Example (curl)

```bash
# Get all expenses
curl "https://dev-api.gt360.app/v1/drivers/{driver_id}/expenses" \
  -H "Authorization: Bearer <token>"

# Get pending expenses for a date range
curl "https://dev-api.gt360.app/v1/drivers/{driver_id}/expenses?status=pending&start_date=2026-02-01&end_date=2026-02-28" \
  -H "Authorization: Bearer <token>"

# Get gas expenses, page 2
curl "https://dev-api.gt360.app/v1/drivers/{driver_id}/expenses?expense_type=gas&page=2&page_size=10" \
  -H "Authorization: Bearer <token>"
```

---

## 3. Get Expenses for Review (Manager)

**`GET /v1/managers/expenses/review`**

Returns expenses pending manager review with filtering and sorting.

### Authentication
- **Role:** `manager`
- **Header:** `Authorization: Bearer <token>`

### Query Parameters

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `driver_id` | UUID | - | Filter by specific driver |
| `expense_type` | string | - | Filter by type |
| `status` | string | - | Filter: `pending`, `verified`, `rejected` |
| `min_amount` | float | - | Minimum amount filter |
| `max_amount` | float | - | Maximum amount filter |
| `sort_by` | string | `created_at` | Sort field: `created_at`, `amount`, `expense_date` |
| `order` | string | `desc` | Sort order: `asc`, `desc` |
| `page` | int | 1 | Page number |
| `page_size` | int | 20 | Items per page |

### Success Response (200)

```json
{
  "expenses": [
    {
      "expense_id": "uuid",
      "driver_id": "uuid",
      "driver_name": "John Doe",
      "amount": 45.50,
      "expense_type": "gas",
      "description": "Fill up at Shell station",
      "expense_date": "2026-02-15",
      "receipt_photo_url": "/uploads/receipts/uuid.jpg",
      "status": "pending",
      "reviewed_at": null,
      "reviewed_by": null,
      "manager_notes": null,
      "rejection_reason": null,
      "created_at": "2026-02-15T10:30:00Z",
      "days_pending": 2
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total_expenses": 3,
    "total_pages": 1
  },
  "summary": {
    "pending_count": 3,
    "pending_total": 185.00,
    "verified_today": 1,
    "rejected_today": 0
  }
}
```

### Example (curl)

```bash
# Get all pending expenses
curl "https://dev-api.gt360.app/v1/managers/expenses/review" \
  -H "Authorization: Bearer <token>"

# Filter by driver and amount range
curl "https://dev-api.gt360.app/v1/managers/expenses/review?driver_id={uuid}&min_amount=20&max_amount=100" \
  -H "Authorization: Bearer <token>"

# Sort by amount ascending
curl "https://dev-api.gt360.app/v1/managers/expenses/review?sort_by=amount&order=asc" \
  -H "Authorization: Bearer <token>"
```

---

## 4. Resolve Expense (Manager)

**`POST /v1/managers/expenses/{expense_id}/resolve`**

Approve, reject, or adjust an expense.

### Authentication
- **Role:** `manager`
- **Header:** `Authorization: Bearer <token>`

### Path Parameters

| Param | Type | Description |
|-------|------|-------------|
| `expense_id` | UUID | Expense ID to resolve |

### Request Body (JSON)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `action` | string | Yes | `verify`, `reject`, or `adjust` |
| `manager_notes` | string | No | Manager's notes |
| `adjusted_amount` | number | If `adjust` | New amount (must be > 0) |
| `adjustment_reason` | string | If `adjust` | Reason for adjustment |
| `rejection_reason` | string | If `reject` | Reason for rejection |

### Actions

| Action | Effect | Required Fields |
|--------|--------|-----------------|
| `verify` | Approves the expense as-is | None |
| `reject` | Rejects the expense | `rejection_reason` |
| `adjust` | Changes amount and approves | `adjusted_amount`, `adjustment_reason` |

### Success Response (200)

```json
{
  "status": "ok",
  "message": "Expense verified successfully",
  "expense": {
    "expense_id": "uuid",
    "driver_id": "uuid",
    "driver_name": "John Doe",
    "amount": 45.50,
    "expense_type": "gas",
    "description": "Fill up at Shell station",
    "expense_date": "2026-02-15",
    "receipt_photo_url": "/uploads/receipts/uuid.jpg",
    "status": "verified",
    "reviewed_at": "2026-02-17T14:00:00Z",
    "reviewed_by": "manager-uuid",
    "manager_notes": "Approved",
    "rejection_reason": null,
    "created_at": "2026-02-15T10:30:00Z",
    "days_pending": 0
  }
}
```

### Error Responses

| Code | Detail |
|------|--------|
| 400 | `Invalid expense ID` |
| 400 | `Expense is not pending review` |
| 400 | `Invalid action. Must be 'verify', 'reject', or 'adjust'` |
| 400 | `rejection_reason is required when rejecting` |
| 400 | `adjusted_amount is required for adjust action` |
| 400 | `Adjusted amount must be greater than 0` |
| 400 | `adjustment_reason is required for adjust action` |
| 401 | `Missing or invalid authentication` |
| 404 | `Expense not found` |

### Examples (curl)

```bash
# Verify an expense
curl -X POST "https://dev-api.gt360.app/v1/managers/expenses/{expense_id}/resolve" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "verify",
    "manager_notes": "Receipt looks good"
  }'

# Reject an expense
curl -X POST "https://dev-api.gt360.app/v1/managers/expenses/{expense_id}/resolve" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "reject",
    "rejection_reason": "Receipt is illegible",
    "manager_notes": "Please resubmit with clearer photo"
  }'

# Adjust and approve
curl -X POST "https://dev-api.gt360.app/v1/managers/expenses/{expense_id}/resolve" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "adjust",
    "adjusted_amount": 40.00,
    "adjustment_reason": "Tax portion not reimbursable",
    "manager_notes": "Adjusted to pre-tax amount"
  }'
```

---

## 5. Get Driver Earnings (Manager)

**`GET /v1/managers/drivers/{driver_id}/earnings`**

Same as the driver earnings endpoint but accessible to managers. See the [Driver Earnings System Guide](./DRIVER_EARNINGS_SYSTEM_GUIDE.md) for full documentation.

### Authentication
- **Role:** `manager`
- **Header:** `Authorization: Bearer <token>`

### Query Parameters

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `start_date` | string | - | Period start (`YYYY-MM-DD`) |
| `end_date` | string | - | Period end (`YYYY-MM-DD`) |
| `page` | int | 1 | Page number |
| `page_size` | int | 10 | Items per page |

---

## Database Schema

### Table: `drivers.driver_expenses`

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | UUID | No | Primary key |
| `driver_id` | UUID | No | FK to `entities.drivers.id` |
| `amount` | DECIMAL | No | Expense amount |
| `expense_type` | VARCHAR(50) | No | Expense category |
| `description` | TEXT | Yes | Optional description |
| `expense_date` | DATE | No | Date of expense |
| `receipt_photo_url` | TEXT | Yes | Path/URL to receipt file |
| `receipt_uploaded` | BOOLEAN | No | Default `false` |
| `status` | VARCHAR(20) | No | `pending`, `verified`, `rejected` |
| `reviewed_at` | TIMESTAMPTZ | Yes | When reviewed |
| `reviewed_by` | UUID | Yes | FK to `entities.users.id` |
| `manager_notes` | TEXT | Yes | Manager's notes |
| `rejection_reason` | TEXT | Yes | Rejection/adjustment reason |
| `pay_period_start` | DATE | Yes | Pay period start |
| `pay_period_end` | DATE | Yes | Pay period end |
| `included_in_payment` | BOOLEAN | No | Default `false` |
| `created_at` | TIMESTAMPTZ | No | Created timestamp |
| `updated_at` | TIMESTAMPTZ | No | Updated timestamp |

---

## Expense Workflow

```
Driver submits expense
        |
        v
   [PENDING] ──── Manager reviews ────┬── verify ──> [VERIFIED]
                                       |
                                       ├── adjust ──> [VERIFIED] (amount changed)
                                       |
                                       └── reject ──> [REJECTED]
```

---

## Frontend Integration

### TypeScript Interfaces

```typescript
interface Expense {
  expense_id: string;
  driver_id: string;
  amount: number;
  expense_type: 'gas' | 'maintenance' | 'parking' | 'tolls' | 'car_wash' | 'supplies' | 'other';
  description: string | null;
  expense_date: string; // YYYY-MM-DD
  receipt_photo_url: string | null;
  receipt_uploaded: boolean;
  status: 'pending' | 'verified' | 'rejected';
  reviewed_at: string | null;
  reviewed_by: string | null;
  manager_notes: string | null;
  rejection_reason: string | null;
  pay_period_start: string | null;
  pay_period_end: string | null;
  included_in_payment: boolean;
  created_at: string;
}

// Manager view adds these fields
interface ManagerExpense extends Expense {
  driver_name: string;
  days_pending: number;
}

interface ExpenseListResponse {
  expenses: Expense[];
  pagination: {
    page: number;
    page_size: number;
    total_expenses: number;
    total_pages: number;
  };
  summary: {
    pending_count: number;
    pending_total: number;
    verified_count: number;
    verified_total: number;
    rejected_count: number;
    rejected_total: number;
  };
}

interface ResolveExpenseRequest {
  action: 'verify' | 'reject' | 'adjust';
  manager_notes?: string;
  adjusted_amount?: number;     // Required if action = 'adjust'
  adjustment_reason?: string;   // Required if action = 'adjust'
  rejection_reason?: string;    // Required if action = 'reject'
}
```

### React Native Example (Submit Expense)

```typescript
const submitExpense = async (
  driverId: string,
  amount: number,
  expenseType: string,
  expenseDate: string,
  description: string | null,
  receiptUri: string,
  token: string
) => {
  const formData = new FormData();
  formData.append('amount', amount.toString());
  formData.append('expense_type', expenseType);
  formData.append('expense_date', expenseDate);
  if (description) formData.append('description', description);

  // Attach receipt photo
  const filename = receiptUri.split('/').pop() || 'receipt.jpg';
  const match = /\.(\w+)$/.exec(filename);
  const type = match ? `image/${match[1]}` : 'image/jpeg';

  formData.append('receipt_photo', {
    uri: receiptUri,
    name: filename,
    type: type,
  } as any);

  const response = await fetch(
    `https://dev-api.gt360.app/v1/drivers/${driverId}/expenses`,
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        // Do NOT set Content-Type — fetch sets it automatically with boundary
      },
      body: formData,
    }
  );

  return await response.json();
};
```

### React Native Example (Get Expenses)

```typescript
const getExpenses = async (
  driverId: string,
  token: string,
  filters?: {
    status?: string;
    start_date?: string;
    end_date?: string;
    expense_type?: string;
    page?: number;
  }
) => {
  const params = new URLSearchParams();
  if (filters?.status) params.append('status', filters.status);
  if (filters?.start_date) params.append('start_date', filters.start_date);
  if (filters?.end_date) params.append('end_date', filters.end_date);
  if (filters?.expense_type) params.append('expense_type', filters.expense_type);
  if (filters?.page) params.append('page', filters.page.toString());

  const query = params.toString() ? `?${params.toString()}` : '';

  const response = await fetch(
    `https://dev-api.gt360.app/v1/drivers/${driverId}/expenses${query}`,
    {
      headers: { 'Authorization': `Bearer ${token}` },
    }
  );

  return await response.json();
};
```

### Kotlin Example (Submit Expense)

```kotlin
suspend fun submitExpense(
    driverId: String,
    amount: Double,
    expenseType: String,
    expenseDate: String,
    description: String?,
    receiptFile: File,
    token: String
): ExpenseResponse {
    val requestBody = MultipartBody.Builder()
        .setType(MultipartBody.FORM)
        .addFormDataPart("amount", amount.toString())
        .addFormDataPart("expense_type", expenseType)
        .addFormDataPart("expense_date", expenseDate)
        .apply { description?.let { addFormDataPart("description", it) } }
        .addFormDataPart(
            "receipt_photo",
            receiptFile.name,
            receiptFile.asRequestBody("image/jpeg".toMediaType())
        )
        .build()

    val request = Request.Builder()
        .url("https://dev-api.gt360.app/v1/drivers/$driverId/expenses")
        .addHeader("Authorization", "Bearer $token")
        .post(requestBody)
        .build()

    return client.newCall(request).execute().parseResponse()
}
```

### Swift Example (Submit Expense)

```swift
func submitExpense(
    driverId: String,
    amount: Double,
    expenseType: String,
    expenseDate: String,
    description: String?,
    receiptData: Data,
    filename: String,
    token: String
) async throws -> ExpenseResponse {
    let boundary = UUID().uuidString
    var request = URLRequest(url: URL(string: "https://dev-api.gt360.app/v1/drivers/\(driverId)/expenses")!)
    request.httpMethod = "POST"
    request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
    request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

    var body = Data()
    func appendField(_ name: String, _ value: String) {
        body.append("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"\r\n\r\n\(value)\r\n".data(using: .utf8)!)
    }
    appendField("amount", String(amount))
    appendField("expense_type", expenseType)
    appendField("expense_date", expenseDate)
    if let desc = description { appendField("description", desc) }

    body.append("--\(boundary)\r\nContent-Disposition: form-data; name=\"receipt_photo\"; filename=\"\(filename)\"\r\nContent-Type: image/jpeg\r\n\r\n".data(using: .utf8)!)
    body.append(receiptData)
    body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)

    request.httpBody = body

    let (data, _) = try await URLSession.shared.data(for: request)
    return try JSONDecoder().decode(ExpenseResponse.self, from: data)
}
```
