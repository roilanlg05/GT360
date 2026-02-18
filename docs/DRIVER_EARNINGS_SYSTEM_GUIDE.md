# Driver Earnings System - Complete Guide

## Table of Contents
1. [Overview](#overview)
2. [System Architecture](#system-architecture)
3. [Data Models](#data-models)
4. [Driver Endpoints](#driver-endpoints)
5. [Manager Endpoints](#manager-endpoints)
6. [Workflows](#workflows)
7. [Calculations](#calculations)
8. [Tax & 1099](#tax--1099)
9. [Error Handling](#error-handling)

---

## Overview

The Driver Earnings System manages driver work sessions (shifts), expense reimbursements, earnings calculations, and tax reporting (1099 forms).

### Key Features
- **Shift Management**: Track driver work sessions with start/end times
- **Expense Tracking**: Submit and review expense reimbursements with receipts
- **Earnings Calculation**: Calculate earnings based on pay type and frequency
- **1099 Generation**: Generate tax forms for year-end reporting
- **Review System**: Manager approval workflow for shifts and expenses

### Pay Types
- **Hourly**: Driver paid per hour worked
- **Daily**: Driver paid per day worked
- **Per Trip**: Driver paid per completed trip

### Pay Frequencies
- **Daily**: Earnings grouped by day
- **Weekly**: Earnings grouped by week (Monday-Sunday)
- **Biweekly**: Earnings grouped by 2-week periods

---

## System Architecture

### Components
```
┌─────────────────────────────────────────────────────────────┐
│                     Driver Earnings System                   │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │    Shifts    │  │   Expenses   │  │   Earnings   │     │
│  │              │  │              │  │              │     │
│  │ - Start/End  │  │ - Submit     │  │ - Calculate  │     │
│  │ - Auto-close │  │ - Review     │  │ - Periods    │     │
│  │ - Review     │  │ - Receipts   │  │ - Breakdown  │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│         │                  │                  │             │
│         └──────────────────┴──────────────────┘             │
│                            │                                │
│                    ┌───────▼────────┐                       │
│                    │  1099 Reports  │                       │
│                    │                │                       │
│                    │ - W-9 Data     │                       │
│                    │ - Tax Calc     │                       │
│                    │ - PDF Gen      │                       │
│                    └────────────────┘                       │
└─────────────────────────────────────────────────────────────┘
```

---

## Data Models

### 1. driver_shifts

Stores driver work sessions.

```sql
CREATE TABLE driver_shifts (
    id UUID PRIMARY KEY,
    driver_id UUID NOT NULL REFERENCES drivers(id),

    -- Pay snapshot (captured at shift start)
    pay_type VARCHAR(10),
    rate DECIMAL,

    -- Schedule snapshot (captured at shift start for daily-rate grouping)
    shift_start_time TIME,
    shift_end_time TIME,

    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,

    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    -- Values: 'active', 'completed', 'auto_closed', 'under_review', 'reviewed'

    -- Review
    review_status VARCHAR(20),
    -- Values: NULL, 'pending', 'approved', 'rejected'

    review_reason TEXT,
    reviewed_at TIMESTAMPTZ,
    reviewed_by UUID REFERENCES users(id),
    manager_notes TEXT,

    auto_closed BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

> **Note**: `pay_type`, `rate`, `shift_start_time`, and `shift_end_time` are snapshots captured when the shift starts. This ensures that if a manager changes the driver's pay or schedule, historical shifts are not affected.

### 2. driver_expenses

Stores expense reimbursement requests.

```sql
CREATE TABLE driver_expenses (
    id UUID PRIMARY KEY,
    driver_id UUID NOT NULL REFERENCES drivers(id),

    -- Expense details
    amount DECIMAL(10, 2) NOT NULL,
    expense_type VARCHAR(50) NOT NULL,
    -- Values: 'gas', 'maintenance', 'parking', 'tolls', 'other'

    description TEXT,
    expense_date DATE NOT NULL,

    -- Receipt
    receipt_photo_url TEXT,
    receipt_uploaded BOOLEAN DEFAULT FALSE,

    -- Review
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- Values: 'pending', 'verified', 'rejected'

    reviewed_at TIMESTAMPTZ,
    reviewed_by UUID REFERENCES users(id),
    manager_notes TEXT,
    rejection_reason TEXT,

    -- Payment period
    pay_period_start DATE,
    pay_period_end DATE,
    included_in_payment BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 3. driver_tax_information

Stores W-9 tax information for 1099 generation.

```sql
CREATE TABLE driver_tax_information (
    id UUID PRIMARY KEY,
    driver_id UUID NOT NULL UNIQUE REFERENCES drivers(id),

    -- TIN (Taxpayer Identification Number)
    tin_type VARCHAR(10) NOT NULL,  -- 'SSN' | 'EIN'
    tin VARCHAR(20) NOT NULL,       -- encrypted

    -- Legal name
    legal_first_name VARCHAR(100) NOT NULL,
    legal_middle_name VARCHAR(100),
    legal_last_name VARCHAR(100) NOT NULL,

    -- Address for 1099
    address_street VARCHAR(255) NOT NULL,
    address_city VARCHAR(100) NOT NULL,
    address_state VARCHAR(2) NOT NULL,
    address_zip VARCHAR(10) NOT NULL,
    address_country VARCHAR(2) DEFAULT 'US',

    -- W-9
    w9_submitted BOOLEAN DEFAULT FALSE,
    w9_submitted_at TIMESTAMPTZ,
    w9_document_url TEXT,

    backup_withholding_rate DECIMAL(5, 2) DEFAULT 0.00,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 4. form_1099_archive

Archives generated 1099 forms.

```sql
CREATE TABLE form_1099_archive (
    id UUID PRIMARY KEY,
    driver_id UUID NOT NULL REFERENCES drivers(id),
    tax_year INT NOT NULL,

    -- Form data
    form_type VARCHAR(20) DEFAULT '1099-NEC',
    box_1_amount DECIMAL(10, 2) NOT NULL,
    box_4_federal_withholding DECIMAL(10, 2) DEFAULT 0.00,

    -- PDF
    pdf_url TEXT,
    pdf_generated_at TIMESTAMPTZ,

    -- IRS submission
    submitted_to_irs BOOLEAN DEFAULT FALSE,
    submitted_at TIMESTAMPTZ,
    confirmation_number VARCHAR(100),

    -- Driver delivery
    sent_to_driver BOOLEAN DEFAULT FALSE,
    sent_to_driver_at TIMESTAMPTZ,
    delivery_method VARCHAR(20),  -- 'email', 'mail', 'portal'

    generated_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_driver_year UNIQUE(driver_id, tax_year)
);
```

---

## Driver Endpoints

All driver endpoints require `role: "driver"` authentication.

### 1. Shift Management

#### Start Shift
**POST** `/v1/drivers/{driver_id}/shifts/start`

Starts a new work shift for the driver.

**Request:**
```json
{
  "started_at": "2026-10-25T08:00:00Z"  // optional, defaults to now
}
```

**Response:**
```json
{
  "status": "ok",
  "message": "Shift started successfully",
  "shift": {
    "shift_id": "uuid",
    "driver_id": "uuid",
    "pay_type": "day",
    "rate": 150.0,
    "started_at": "2026-10-25T08:00:00Z",
    "ended_at": null,
    "duration_hours": null,
    "status": "active",
    "review_status": null,
    "auto_closed": false,
    "crosses_midnight": false,
    "trips_in_shift": 0,
    "hours_distribution": null,
    "created_at": "2026-10-25T08:00:00Z"
  }
}
```

**Validations:**
- Driver must not have another active shift
- Driver must be active (`is_active = true`)

**Errors:**
- `409`: "Driver already has an active shift"
- `403`: "Driver is not active"

---

#### End Shift
**POST** `/v1/drivers/{driver_id}/shifts/end`

Ends the active work shift for the driver.

**Request:**
```json
{
  "ended_at": "2026-10-25T16:00:00Z"  // optional, defaults to now
}
```

**Response:**
```json
{
  "status": "ok",
  "message": "Shift ended successfully",
  "shift": {
    "shift_id": "uuid",
    "driver_id": "uuid",
    "pay_type": "day",
    "rate": 150.0,
    "started_at": "2026-10-25T08:00:00Z",
    "ended_at": "2026-10-25T16:00:00Z",
    "duration_hours": 8.0,
    "status": "completed",
    "review_status": null,
    "auto_closed": false,
    "crosses_midnight": false,
    "trips_in_shift": 5,
    "hours_distribution": null,
    "created_at": "2026-10-25T08:00:00Z"
  }
}
```

**Validations:**
- Driver must have an active shift
- `ended_at` must be after `started_at`
- If shift > 6 hours, it may be auto-closed

**Errors:**
- `404`: "No active shift found"
- `400`: "Invalid end time"

---

#### Get My Shifts
**GET** `/v1/drivers/{driver_id}/shifts`

Get driver's shift history.

**Query Parameters:**
- `page` (int, default: 1)
- `page_size` (int, default: 20)
- `start_date` (date, optional)
- `end_date` (date, optional)
- `status` (string, optional): 'active', 'completed', 'under_review'

**Response:**
```json
{
  "shifts": [
    {
      "shift_id": "uuid",
      "driver_id": "uuid",
      "pay_type": "day",
      "rate": 150.0,
      "started_at": "2026-10-25T08:00:00Z",
      "ended_at": "2026-10-25T16:00:00Z",
      "duration_hours": 8.0,
      "status": "completed",
      "review_status": null,
      "review_reason": null,
      "reviewed_at": null,
      "reviewed_by": null,
      "manager_notes": null,
      "auto_closed": false,
      "crosses_midnight": false,
      "trips_in_shift": 5,
      "hours_distribution": null,
      "created_at": "2026-10-25T08:00:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total_shifts": 50,
    "total_pages": 3
  },
  "summary": {
    "active_shifts": 0,
    "completed_shifts": 48,
    "under_review_shifts": 2
  }
}
```

> **Note**: `trips_in_shift` counts completed trips from `trips_history` that have `dropped_off_at` within the shift's time window. For active shifts (no `ended_at`), the current time is used as the upper bound, so the count updates in real-time as trips are completed.

---

### 2. Expense Management

#### Submit Expense
**POST** `/v1/drivers/{driver_id}/expenses`

Submit an expense reimbursement request with receipt.

**Request:** (multipart/form-data)
```
amount: 45.50
expense_type: gas
description: Gas fill at Shell station
expense_date: 2026-10-25
receipt_photo: [file upload - JPEG/PNG/PDF, max 10MB]
```

**Response:**
```json
{
  "status": "ok",
  "message": "Expense submitted for review",
  "expense": {
    "expense_id": "uuid",
    "driver_id": "uuid",
    "amount": 45.50,
    "expense_type": "gas",
    "description": "Gas fill at Shell station",
    "expense_date": "2026-10-25",
    "receipt_photo_url": "https://storage.example.com/receipts/uuid.jpg",
    "status": "pending",
    "created_at": "2026-10-26T08:00:00Z"
  }
}
```

**Validations:**
- `amount` > 0
- `expense_date` cannot be in the future
- `expense_date` cannot be more than 30 days in the past
- `receipt_photo` is required
- Driver must be active

**Errors:**
- `400`: "Invalid amount"
- `400`: "Expense date cannot be in the future"
- `400`: "Receipt photo is required"
- `413`: "Receipt file too large (max 10MB)"

---

#### Get My Expenses
**GET** `/v1/drivers/{driver_id}/expenses`

Get driver's expense history.

**Query Parameters:**
- `page` (int, default: 1)
- `page_size` (int, default: 20)
- `status` (string, optional): 'pending', 'verified', 'rejected', 'all'
- `start_date` (date, optional)
- `end_date` (date, optional)
- `expense_type` (string, optional)

**Response:**
```json
{
  "expenses": [
    {
      "expense_id": "uuid",
      "amount": 45.50,
      "expense_type": "gas",
      "description": "Gas fill at Shell station",
      "expense_date": "2026-10-25",
      "receipt_photo_url": "https://...",
      "status": "verified",
      "reviewed_at": "2026-10-26T14:00:00Z",
      "manager_notes": "Approved",
      "created_at": "2026-10-26T08:00:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total_expenses": 45,
    "total_pages": 3
  },
  "summary": {
    "pending_count": 3,
    "pending_total": 120.00,
    "verified_count": 40,
    "verified_total": 1850.50,
    "rejected_count": 2,
    "rejected_total": 25.00
  }
}
```

---

### 3. Earnings

#### Get My Earnings
**GET** `/v1/drivers/{driver_id}/earnings`

Get earnings breakdown by pay period.

**Query Parameters:**
- `page` (int, default: 1)
- `page_size` (int, default: 10)
- `start_date` (date, optional)
- `end_date` (date, optional)

**Response:**
```json
{
  "driver_id": "uuid",
  "driver_name": "John Doe",
  "pay_type": "day",
  "pay_frequency": "biweekly",
  "rate": 150.00,
  "timezone": "America/Kentucky/Louisville",

  "periods": [
    {
      "period_start": "2026-02-16",
      "period_end": "2026-03-01",

      "gross_earnings": 150.00,
      "verified_expenses": 0.0,
      "net_pay": 150.00,

      "total_hours": 2.92,
      "total_days": 1,
      "total_trips": 6,
      "total_shifts": 6,
      "expenses_count": 0,

      "shifts": [
        {
          "id": "uuid",
          "started_at": "2026-02-17T12:40:24+00:00",
          "ended_at": "2026-02-17T12:42:57+00:00",
          "status": "completed",
          "pay_type": "day",
          "rate": 150.0,
          "hours": 0.04,
          "trips_in_shift": 0
        },
        {
          "id": "uuid",
          "started_at": "2026-02-17T16:18:03+00:00",
          "ended_at": null,
          "status": "active",
          "pay_type": "day",
          "rate": 150.0,
          "hours": 0,
          "trips_in_shift": 1
        }
      ],

      "trips": [
        {
          "id": "uuid",
          "pick_up_date": "2026-02-17",
          "pick_up_time": "04:15:00",
          "pick_up_location": "Hyatt Regency Louisville",
          "drop_off_location": "SDF",
          "dropped_off_at": "2026-02-17T09:32:14+00:00",
          "airline": "WN",
          "flight_number": "3478"
        }
      ],

      "expenses": [
        {
          "id": "uuid",
          "amount": 45.50,
          "expense_type": "gas",
          "description": "Gas fill",
          "expense_date": "2026-02-17",
          "status": "verified",
          "receipt_photo_url": "/uploads/receipts/uuid.jpg"
        }
      ]
    }
  ],

  "pagination": {
    "page": 1,
    "page_size": 10,
    "total_periods": 2,
    "total_pages": 1
  },

  "year_to_date": {
    "year": 2026,
    "total_gross_earnings": 150.00,
    "total_expenses_reimbursed": 0.0,
    "total_net_pay": 150.00,
    "total_hours_worked": 2.92,
    "total_days_worked": 1,
    "total_trips": 6
  }
}
```

**Key behaviors:**
- **`total_trips`**: Counts ALL completed trips in the period from `trips_history` table, regardless of whether they occurred during a shift or not.
- **`trips_in_shift`**: Counts only trips completed during that specific shift's time window (from `trips_history`).
- **Active shifts are included**: The current active shift appears in the period with `ended_at: null`, `status: "active"`, and its `trips_in_shift` counts trips from shift start to now.
- **Hours and days for active shifts**: Calculated using `now()` as the end time.
- **Trips data source**: All trip data comes from `trips.trips_history` (completed trips are archived there from `trips.trips`).

---

### 4. Tax Information

#### Submit W-9 / Tax Information
**POST** `/v1/drivers/{driver_id}/tax-information`

Submit tax information for 1099 generation (W-9 data).

**Request:** (multipart/form-data)
```
legal_first_name: John
legal_middle_name: Michael
legal_last_name: Doe
tin_type: SSN
tin: 987-65-4321
address_street: 456 Driver St
address_city: Miami
address_state: FL
address_zip: 33102
w9_document: [file upload - PDF of signed W-9]
```

**Response:**
```json
{
  "status": "ok",
  "message": "Tax information submitted successfully",
  "tax_info": {
    "tax_info_id": "uuid",
    "driver_id": "uuid",
    "tin_type": "SSN",
    "tin_masked": "***-**-4321",
    "legal_name": "John Michael Doe",
    "address": "456 Driver St, Miami, FL 33102",
    "w9_submitted": true,
    "w9_document_url": "https://..."
  }
}
```

**Validations:**
- All fields required
- `tin` must be valid format (SSN: XXX-XX-XXXX, EIN: XX-XXXXXXX)
- `address_state` must be valid 2-letter state code
- `w9_document` must be PDF

**Errors:**
- `400`: "Invalid TIN format"
- `400`: "Invalid state code"
- `409`: "Tax information already exists for this driver"

---

#### Get My 1099
**GET** `/v1/drivers/{driver_id}/1099`

Get 1099-NEC form data for the driver.

**Query Parameters:**
- `year` (int, required): tax year (e.g., 2026)
- `format` (string, optional): 'json' | 'pdf' (default: 'json')

**Response:** (format=json)
```json
{
  "form_type": "1099-NEC",
  "tax_year": 2026,
  "generated_at": "2027-01-15T10:00:00Z",

  "payer": {
    "name": "GT360 Transportation LLC",
    "ein": "12-3456789",
    "address": {
      "street": "123 Business Ave",
      "city": "Miami",
      "state": "FL",
      "zip": "33101"
    },
    "phone": "+1-555-0100"
  },

  "recipient": {
    "name": "John Michael Doe",
    "tin": "987-65-4321",
    "tin_type": "SSN",
    "tin_masked": "***-**-4321",
    "address": {
      "street": "456 Driver St",
      "city": "Miami",
      "state": "FL",
      "zip": "33102"
    }
  },

  "form_data": {
    "box_1_nonemployee_compensation": 10400.00,
    "box_2_payer_made_direct_sales": null,
    "box_4_federal_income_tax_withheld": 0.00,
    "box_5_state_tax_withheld": 0.00,
    "box_6_state_payers_state_no": null,
    "box_7_state_income": 10400.00
  },

  "earnings_breakdown": {
    "total_gross_earnings": 10400.00,
    "total_hours_worked": 1040.0,
    "total_days_worked": 130,
    "total_trips": 520,
    "pay_type": "hourly",
    "rate": 10.00
  },

  "expenses_summary": {
    "total_expenses_reimbursed": 1850.50,
    "note": "Expenses are business reimbursements and not included in Box 1"
  },

  "payment_summary": {
    "total_gross_earnings": 10400.00,
    "total_expenses_reimbursed": 1850.50,
    "total_paid_to_driver": 12250.50,
    "total_reported_on_1099": 10400.00
  },

  "compliance": {
    "minimum_reporting_threshold": 600.00,
    "requires_1099": true,
    "form_due_date": "2027-01-31",
    "recipient_copy_due_date": "2027-01-31"
  }
}
```

**Response:** (format=pdf)
- Returns PDF file with proper headers
- `Content-Type: application/pdf`
- `Content-Disposition: attachment; filename="1099-NEC_2026_{driver_id}.pdf"`

**Validations:**
- Driver must have tax information on file
- Year must be current year or previous years (not future)
- Earnings must be >= $600 to generate 1099

**Errors:**
- `400`: "Tax information not found. Please complete W-9 first."
- `400`: "No earnings found for year {year}"
- `400`: "Earnings below $600 threshold. 1099 not required."

---

## Manager Endpoints

All manager endpoints require `role: "manager"` authentication.

### 1. Shift Review

#### Get Shifts Pending Review
**GET** `/v1/managers/shifts/review`

Get list of shifts that need manager review.

**Query Parameters:**
- `page` (int, default: 1)
- `page_size` (int, default: 20)
- `driver_id` (uuid, optional): filter by specific driver
- `status` (string, optional): 'pending', 'approved', 'rejected'
- `sort_by` (string, default: 'created_at'): 'created_at', 'started_at', 'driver_name'
- `order` (string, default: 'desc'): 'asc', 'desc'

**Response:**
```json
{
  "shifts": [
    {
      "shift_id": "uuid",
      "driver_id": "uuid",
      "driver_name": "John Doe",
      "started_at": "2026-10-25T16:00:00Z",
      "ended_at": "2026-10-26T04:00:00Z",
      "duration_hours": 12.0,
      "auto_closed": true,
      "review_status": "pending",
      "review_reason": "Auto-closed after 6 hours of inactivity",
      "created_at": "2026-10-25T16:00:00Z",
      "trips_in_shift": 5,
      "hours_distribution": {
        "2026-10-25": 8.0,
        "2026-10-26": 4.0
      }
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total_shifts": 15,
    "total_pages": 1
  },
  "summary": {
    "pending_count": 10,
    "approved_count": 3,
    "rejected_count": 2
  }
}
```

---

#### Resolve Shift Review
**POST** `/v1/managers/shifts/{shift_id}/resolve`

Approve, reject, or adjust a shift under review.

**Request:**
```json
{
  "action": "approve",
  "manager_notes": "Verified with driver, shift was correct",
  "adjusted_ended_at": "2026-10-26T02:00:00Z"
}
```

**Actions:**
- `approve`: Accept shift as-is
- `reject`: Reject the shift (won't count for earnings)
- `adjust`: Modify the `ended_at` time and approve

**Response:**
```json
{
  "status": "ok",
  "message": "Shift approved successfully",
  "shift": {
    "shift_id": "uuid",
    "status": "reviewed",
    "review_status": "approved",
    "reviewed_at": "2026-10-27T10:30:00Z",
    "reviewed_by": "manager-uuid",
    "started_at": "2026-10-25T16:00:00Z",
    "ended_at": "2026-10-26T04:00:00Z",
    "duration_hours": 12.0,
    "manager_notes": "Verified with driver, shift was correct"
  }
}
```

**Validations:**
- Shift must be `under_review` status
- `adjusted_ended_at` must be after `started_at` (if adjusting)
- Manager must have permission

**Errors:**
- `404`: "Shift not found"
- `400`: "Shift is not under review"
- `400`: "Invalid adjusted end time"

---

### 2. Expense Review

#### Get Expenses Pending Review
**GET** `/v1/managers/expenses/review`

Get list of expenses that need manager review.

**Query Parameters:**
- `page` (int, default: 1)
- `page_size` (int, default: 20)
- `driver_id` (uuid, optional)
- `expense_type` (string, optional): 'gas', 'maintenance', etc.
- `status` (string, optional): 'pending', 'verified', 'rejected'
- `min_amount` (decimal, optional)
- `max_amount` (decimal, optional)
- `sort_by` (string, default: 'created_at')
- `order` (string, default: 'desc'): 'asc', 'desc'

**Response:**
```json
{
  "expenses": [
    {
      "expense_id": "uuid",
      "driver_id": "uuid",
      "driver_name": "John Doe",
      "amount": 45.50,
      "expense_type": "gas",
      "description": "Gas fill at Shell station",
      "expense_date": "2026-10-25",
      "receipt_photo_url": "https://...",
      "status": "pending",
      "created_at": "2026-10-26T08:00:00Z",
      "days_pending": 1
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total_expenses": 15,
    "total_pages": 1
  },
  "summary": {
    "pending_count": 15,
    "pending_total": 680.50,
    "verified_today": 10,
    "rejected_today": 2
  }
}
```

---

#### Resolve Expense Review
**POST** `/v1/managers/expenses/{expense_id}/resolve`

Approve, reject, or adjust an expense.

**Request:**
```json
{
  "action": "verify",
  "manager_notes": "Receipt verified, approved",
  "adjusted_amount": 40.00,
  "adjustment_reason": "Receipt shows $40, not $45.50",
  "rejection_reason": "Receipt is not legible"
}
```

**Actions:**
- `verify`: Approve expense as-is
- `reject`: Reject the expense
- `adjust`: Modify the amount and approve

**Response:**
```json
{
  "status": "ok",
  "message": "Expense verified successfully",
  "expense": {
    "expense_id": "uuid",
    "status": "verified",
    "amount": 45.50,
    "reviewed_at": "2026-10-26T14:00:00Z",
    "reviewed_by": "manager-uuid",
    "manager_notes": "Receipt verified, approved"
  }
}
```

**Validations:**
- Expense must be `pending` status
- `adjusted_amount` must be > 0 (if adjusting)
- `rejection_reason` required if rejecting
- Manager must have permission

**Errors:**
- `404`: "Expense not found"
- `400`: "Expense is not pending review"
- `400`: "Rejection reason required when rejecting"

---

### 3. Driver Earnings (Manager View)

#### Get Driver Earnings
**GET** `/v1/managers/drivers/{driver_id}/earnings`

Get earnings for any driver (same response as driver endpoint).

Query parameters and response are identical to the driver endpoint.

---

### 4. 1099 Management

#### Get Bulk 1099 Data
**GET** `/v1/managers/1099/bulk`

Get 1099 data for all drivers.

**Query Parameters:**
- `year` (int, required): 2026
- `format` (string): 'json' | 'csv'
- `min_earnings` (decimal, optional, default: 600): only drivers with earnings >= this
- `driver_ids` (list[uuid], optional): filter specific drivers

**Response:**
```json
{
  "tax_year": 2026,
  "generated_at": "2027-01-15T10:00:00Z",
  "total_drivers": 25,
  "total_earnings_reported": 260000.00,
  "total_expenses_reimbursed": 38500.00,
  "total_paid_to_drivers": 298500.00,

  "drivers": [
    {
      "driver_id": "uuid",
      "driver_name": "John Doe",
      "tin": "***-**-4321",
      "box_1_amount": 10400.00,
      "expenses_reimbursed": 1850.50,
      "total_paid": 12250.50,
      "requires_1099": true,
      "has_tax_info": true,
      "download_url": "/api/v1/drivers/{id}/1099?year=2026&format=pdf"
    }
  ],

  "bulk_download_url": "/api/v1/managers/1099/bulk/download?year=2026&format=zip"
}
```

---

#### Generate All 1099 PDFs
**POST** `/v1/managers/1099/generate-all`

Generate PDF 1099 forms for all eligible drivers.

**Request:**
```json
{
  "year": 2026,
  "min_earnings": 600.00
}
```

**Response:**
```json
{
  "status": "ok",
  "message": "1099 forms generation started",
  "job_id": "uuid",
  "total_drivers": 25,
  "estimated_completion": "2027-01-15T10:30:00Z"
}
```

This is an async job that generates PDFs in the background.

---

## Workflows

### 1. Normal Shift Flow

```
1. Driver → POST /shifts/start
   ↓
2. Driver works and completes trips
   (Active shift already visible in earnings with real-time trip count)
   ↓
3. Driver → POST /shifts/end
   ↓
4. Shift marked as 'completed'
   ↓
5. Shift counts in earnings calculation
```

> **Note**: Active shifts are included in earnings in real-time. The `trips_in_shift` count updates as trips are completed, and hours/days are calculated using the current time as the end boundary.

---

### 2. Auto-Closed Shift Flow

```
1. Driver → POST /shifts/start
   ↓
2. Driver forgets to end shift
   ↓
3. Auto-close job runs (after 6 hours)
   ↓
4. Shift auto-closed and marked 'under_review'
   ↓
5. Manager → GET /managers/shifts/review
   ↓
6. Manager → POST /managers/shifts/{id}/resolve
   ↓
7. If approved: counts in earnings
   If rejected: doesn't count
```

---

### 3. Expense Submission Flow

```
1. Driver pays for gas
   ↓
2. Driver → POST /expenses (with receipt photo)
   ↓
3. Expense marked as 'pending'
   ↓
4. Manager → GET /managers/expenses/review
   ↓
5. Manager reviews receipt photo
   ↓
6. Manager → POST /managers/expenses/{id}/resolve
   ↓
7. If verified: added to net_pay in earnings
   If rejected: not included
```

---

### 4. 1099 Generation Flow

```
1. Driver → POST /tax-information (W-9 data)
   ↓
2. Year ends (December 31)
   ↓
3. System calculates annual gross earnings
   ↓
4. Driver → GET /1099?year=2026
   ↓
5. System generates 1099-NEC
   ↓
6. Driver downloads PDF
   ↓
7. Manager → POST /managers/1099/generate-all
   ↓
8. All 1099s archived and sent to IRS
```

---

## Calculations

### 1. Earnings by Pay Type

#### Hourly
```
earnings = total_hours_worked × hourly_rate

Example:
- 40 hours × $10/hour = $400
```

#### Daily
```
earnings = unique_work_days × daily_rate

Example:
- 5 unique work days × $80/day = $400
```

**Work Day Grouping**: Multiple shifts on the same day are grouped into a single "work day" so the driver is charged once per day, not once per shift. For example, a driver with a $120/day rate who opens/closes 4 shifts in one day is charged $120 (1 day), not $480 (4 shifts).

**Overnight schedules**: If the driver's schedule crosses midnight (e.g. 9PM-3AM), shifts started after midnight but before the schedule end time are grouped with the previous day's work day. This is determined by the `shift_start_time` and `shift_end_time` snapshotted on each shift.

#### Per Trip
```
earnings = trips_completed_within_shifts × trip_rate

Example:
- 20 trips × $20/trip = $400
```

> **Note**: For per-trip pay calculation, only trips completed within a shift's time window count toward earnings. However, `total_trips` in the period summary counts ALL completed trips from `trips_history` regardless of shifts.

---

### 2. Shifts Crossing Midnight

When a shift crosses midnight (e.g., 4 PM → 4 AM next day):

```python
# Shift: 4:00 PM Oct 25 → 4:00 AM Oct 26

hours_per_day = {
  "2026-10-25": 8.0,  # 4pm-12am
  "2026-10-26": 4.0   # 12am-4am
}

# For daily pay frequency:
day_1_earnings = 8.0 × rate
day_2_earnings = 4.0 × rate
```

---

### 3. Pay Periods

#### Daily
```
Period = Single day
Start: 00:00:00 (in driver's timezone)
End: 23:59:59 (in driver's timezone)
```

#### Weekly
```
Period = Monday to Sunday
Start: Monday 00:00:00
End: Sunday 23:59:59
```

#### Biweekly
```
Period = 2 weeks (14 days)
Start: Monday of week 1 00:00:00
End: Sunday of week 2 23:59:59

Year has 26 biweekly periods
```

---

### 4. Net Pay Calculation

```
Net Pay = Gross Earnings + Verified Expenses

Example:
- Gross Earnings: $800 (from shifts/trips)
- Verified Expenses: $150 (gas reimbursement)
- Net Pay: $950 (what driver receives)
```

---

### 5. 1099 Box 1 Calculation

```
Box 1 = Gross Earnings ONLY (expenses NOT included)

Example:
- Gross Earnings: $800
- Expenses: $150
- Box 1: $800 (NOT $950)

Reason: Expense reimbursements are not taxable income
```

---

## Tax & 1099

### 1099-NEC Form

The 1099-NEC (Nonemployee Compensation) is used to report payments to independent contractors.

#### When Required
- Payments >= $600 in a calendar year
- Paid to non-employees (contractors, not W-2 employees)

#### Key Boxes
- **Box 1**: Nonemployee compensation (gross earnings only)
- **Box 4**: Federal income tax withheld (usually $0 for contractors)

#### Due Dates
- **January 31**: Deadline to provide copy to recipient (driver)
- **January 31**: Deadline to file with IRS

---

### Gross vs Net

#### For Driver (what they receive):
```
Net Pay = Gross Earnings + Reimbursements

Driver receives: $950
```

#### For IRS (what's taxable):
```
1099 Box 1 = Gross Earnings only

Taxable: $800
Non-taxable reimbursements: $150
```

---

### W-9 Requirement

Before generating 1099, driver must submit W-9 information:
- Legal name
- TIN (SSN or EIN)
- Address
- Signature (W-9 document upload)

This is required by IRS to issue 1099 forms.

---

## Error Handling

### Common Error Codes

#### 400 - Bad Request
- Invalid input data
- Validation errors
- Business rule violations

```json
{
  "detail": "Invalid amount. Must be greater than 0."
}
```

#### 401 - Unauthorized
- Missing or invalid authentication token

```json
{
  "detail": "Missing or invalid authentication"
}
```

#### 403 - Forbidden
- User doesn't have permission
- Driver not active

```json
{
  "detail": "Driver is not active"
}
```

#### 404 - Not Found
- Resource doesn't exist

```json
{
  "detail": "Shift not found"
}
```

#### 409 - Conflict
- Resource already exists
- Conflicting state

```json
{
  "detail": "Driver already has an active shift"
}
```

#### 413 - Payload Too Large
- File upload too large

```json
{
  "detail": "Receipt file too large (max 10MB)"
}
```

#### 500 - Internal Server Error
- Server error
- Unexpected exceptions

```json
{
  "detail": "Internal server error"
}
```

---

### Field Validation Errors

When multiple fields have validation errors:

```json
{
  "detail": [
    {
      "field": "amount",
      "error": "Must be greater than 0"
    },
    {
      "field": "expense_date",
      "error": "Cannot be in the future"
    }
  ]
}
```

---

## Auto-Close Job

A background job runs every 30 minutes to auto-close stale shifts.

### Logic
```python
# Find active shifts older than 6 hours
cutoff = now - 6 hours

for shift in active_shifts_older_than(cutoff):
    shift.ended_at = shift.started_at + 6 hours
    shift.status = 'under_review'
    shift.review_status = 'pending'
    shift.auto_closed = True
    shift.review_reason = "Auto-closed after 6 hours of inactivity"

    notify_driver(shift)
    notify_manager(shift)
```

### Notification
- Driver receives notification: "Your shift was auto-closed after 6 hours"
- Manager receives notification: "New shift pending review"

---

## Timezone Handling

All calculations use the driver's assigned location timezone.

### Getting Driver Timezone
```python
driver.assigned_location → location.timezone
# Example: "America/New_York"
```

### Period Boundaries
Periods (daily/weekly/biweekly) are calculated in driver's local timezone, then converted to UTC for database queries.

```python
# Example: Weekly period
local_tz = pytz.timezone("America/New_York")
week_start = local_tz.localize(datetime(2026, 10, 25, 0, 0, 0))  # Monday 12am ET
week_end = local_tz.localize(datetime(2026, 11, 1, 23, 59, 59))   # Sunday 11:59pm ET

# Convert to UTC for queries
week_start_utc = week_start.astimezone(timezone.utc)
week_end_utc = week_end.astimezone(timezone.utc)
```

---

## Security & Privacy

### TIN (SSN/EIN) Encryption
- TIN is encrypted in database
- Only show masked version in API responses: `***-**-4321`
- Full TIN only visible in PDF generation and IRS submission

### Receipt Photos
- Stored in secure S3 bucket with encryption
- Access controlled by driver_id
- Only driver and managers can view

### Audit Logs
All manager actions (approve/reject) are logged:
- Who performed the action
- When
- What was changed
- Notes provided

---

## Rate Limiting

### Driver Endpoints
- Start/End shift: 10 requests per minute
- Submit expense: 5 requests per minute
- Get earnings: 20 requests per minute

### Manager Endpoints
- Review endpoints: 60 requests per minute
- Bulk operations: 10 requests per minute

---

## File Upload Limits

### Receipt Photos
- Max size: 10 MB
- Formats: JPEG, PNG, PDF
- Resolution: Recommended 300 DPI for receipts

### W-9 Documents
- Max size: 5 MB
- Format: PDF only
- Must be signed

---

## API Versioning

Current version: **v1**

All endpoints prefixed with `/v1/`

Breaking changes will be released as new versions (/v2/, etc.) with deprecation notices.

---

## Support & Contact

For questions or issues with the Earnings System:
- Technical support: tech@gt360.com
- Driver support: support@gt360.com
- Manager inquiries: managers@gt360.com

---

**End of Documentation**
