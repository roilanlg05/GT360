# 📱 Frontend Integration Guide - Driver Earnings System

> Complete guide for integrating the Driver Earnings System in your frontend application.

## 📋 Table of Contents

- [Authentication](#authentication)
- [Driver Endpoints](#driver-endpoints)
  - [Shifts Management](#shifts-management)
  - [Expenses Management](#expenses-management)
  - [Earnings View](#earnings-view)
  - [Tax Information](#tax-information)
- [Manager Endpoints](#manager-endpoints)
  - [Shift Review](#shift-review)
  - [Expense Review](#expense-review)
  - [Driver Earnings View](#driver-earnings-view-manager)
  - [1099 Management](#1099-management)
- [Error Handling](#error-handling)
- [Frontend Examples](#frontend-examples)

---

## 🔐 Authentication

All endpoints require JWT authentication via Bearer token.

### Headers Required:
```javascript
{
  "Authorization": "Bearer YOUR_JWT_TOKEN",
  "Content-Type": "application/json" // or "multipart/form-data" for file uploads
}
```

### Getting the Token:
```javascript
// Login endpoint
POST /v1/auth/sign-in
Body: {
  "email": "driver@example.com",
  "password": "password"
}

Response: {
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type": "bearer"
}
```

---

# 👨‍✈️ DRIVER ENDPOINTS

## Shifts Management

### 1. Start Shift

**Endpoint:** `POST /v1/drivers/{driver_id}/shifts/start`

**Description:** Starts a new shift for the driver. Only one shift can be active at a time.

**Path Parameters:**
- `driver_id` (UUID, required): The driver's ID

**Headers:**
```
Authorization: Bearer {token}
Content-Type: application/json
```

**Request Body:**
```json
{}
```
*Empty object - no additional parameters needed*

**Success Response (200):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "driver_id": "8f83da7b-7d21-4d49-891e-1ed75d411e4d",
  "started_at": "2026-02-16T14:30:00Z",
  "ended_at": null,
  "status": "active",
  "review_status": null,
  "auto_closed": false,
  "manager_notes": null,
  "resolved_at": null,
  "resolved_by": null,
  "created_at": "2026-02-16T14:30:00Z",
  "updated_at": "2026-02-16T14:30:00Z"
}
```

**Error Responses:**

*400 - Already has active shift:*
```json
{
  "detail": "Driver already has an active shift"
}
```

*403 - Unauthorized:*
```json
{
  "detail": "Not authorized to start shift for this driver"
}
```

**Frontend Example (React + Axios):**
```javascript
const startShift = async (driverId, token) => {
  try {
    const response = await axios.post(
      `${API_URL}/v1/drivers/${driverId}/shifts/start`,
      {},
      {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      }
    );

    console.log('Shift started:', response.data);
    return response.data;
  } catch (error) {
    if (error.response?.status === 400) {
      alert('You already have an active shift!');
    }
    throw error;
  }
};
```

**Frontend Example (React Native + Fetch):**
```javascript
const startShift = async (driverId, token) => {
  try {
    const response = await fetch(
      `${API_URL}/v1/drivers/${driverId}/shifts/start`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({})
      }
    );

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail);
    }

    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Error starting shift:', error);
    throw error;
  }
};
```

---

### 2. End Shift

**Endpoint:** `POST /v1/drivers/{driver_id}/shifts/end`

**Description:** Ends the currently active shift for the driver.

**Path Parameters:**
- `driver_id` (UUID, required): The driver's ID

**Headers:**
```
Authorization: Bearer {token}
Content-Type: application/json
```

**Request Body:**
```json
{}
```

**Success Response (200):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "driver_id": "8f83da7b-7d21-4d49-891e-1ed75d411e4d",
  "started_at": "2026-02-16T14:30:00Z",
  "ended_at": "2026-02-16T22:15:00Z",
  "status": "completed",
  "review_status": "approved",
  "auto_closed": false,
  "manager_notes": null,
  "resolved_at": null,
  "resolved_by": null,
  "created_at": "2026-02-16T14:30:00Z",
  "updated_at": "2026-02-16T22:15:00Z"
}
```

**Error Responses:**

*400 - No active shift:*
```json
{
  "detail": "No active shift found to end"
}
```

**Frontend Example:**
```javascript
const endShift = async (driverId, token) => {
  try {
    const response = await axios.post(
      `${API_URL}/v1/drivers/${driverId}/shifts/end`,
      {},
      {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      }
    );

    return response.data;
  } catch (error) {
    if (error.response?.status === 400) {
      alert('No active shift to end!');
    }
    throw error;
  }
};
```

---

### 3. Get Shift History

**Endpoint:** `GET /v1/drivers/{driver_id}/shifts`

**Description:** Retrieves paginated shift history for the driver.

**Path Parameters:**
- `driver_id` (UUID, required): The driver's ID

**Query Parameters:**
- `page` (integer, optional, default: 1): Page number
- `page_size` (integer, optional, default: 10, max: 100): Items per page
- `status` (string, optional): Filter by status ("active", "completed", "pending_review")

**Headers:**
```
Authorization: Bearer {token}
```

**Success Response (200):**
```json
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "driver_id": "8f83da7b-7d21-4d49-891e-1ed75d411e4d",
      "started_at": "2026-02-16T14:30:00Z",
      "ended_at": "2026-02-16T22:15:00Z",
      "status": "completed",
      "review_status": "approved",
      "auto_closed": false,
      "manager_notes": null,
      "resolved_at": "2026-02-17T09:00:00Z",
      "resolved_by": "manager-uuid",
      "created_at": "2026-02-16T14:30:00Z",
      "updated_at": "2026-02-16T22:15:00Z"
    },
    {
      "id": "660e8400-e29b-41d4-a716-446655440001",
      "driver_id": "8f83da7b-7d21-4d49-891e-1ed75d411e4d",
      "started_at": "2026-02-15T08:00:00Z",
      "ended_at": "2026-02-15T16:30:00Z",
      "status": "completed",
      "review_status": "approved",
      "auto_closed": false,
      "manager_notes": "Good work!",
      "resolved_at": "2026-02-16T09:00:00Z",
      "resolved_by": "manager-uuid",
      "created_at": "2026-02-15T08:00:00Z",
      "updated_at": "2026-02-15T16:30:00Z"
    }
  ],
  "total": 45,
  "page": 1,
  "page_size": 10,
  "total_pages": 5
}
```

**Frontend Example (with filtering):**
```javascript
const getShiftHistory = async (driverId, token, filters = {}) => {
  const params = new URLSearchParams({
    page: filters.page || 1,
    page_size: filters.pageSize || 10,
    ...(filters.status && { status: filters.status })
  });

  try {
    const response = await axios.get(
      `${API_URL}/v1/drivers/${driverId}/shifts?${params}`,
      {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      }
    );

    return response.data;
  } catch (error) {
    console.error('Error fetching shifts:', error);
    throw error;
  }
};

// Usage:
const shifts = await getShiftHistory(driverId, token, {
  page: 1,
  pageSize: 20,
  status: 'completed'
});
```

**UI Example (React Component):**
```jsx
function ShiftHistory({ driverId, token }) {
  const [shifts, setShifts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);

  useEffect(() => {
    const fetchShifts = async () => {
      setLoading(true);
      try {
        const data = await getShiftHistory(driverId, token, { page });
        setShifts(data.items);
      } catch (error) {
        console.error(error);
      } finally {
        setLoading(false);
      }
    };

    fetchShifts();
  }, [page]);

  return (
    <div>
      {loading ? (
        <Spinner />
      ) : (
        <ul>
          {shifts.map(shift => (
            <li key={shift.id}>
              Started: {new Date(shift.started_at).toLocaleString()}
              <br />
              Ended: {shift.ended_at ? new Date(shift.ended_at).toLocaleString() : 'Active'}
              <br />
              Status: {shift.status}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

---

## Expenses Management

### 1. Submit Expense

**Endpoint:** `POST /v1/drivers/{driver_id}/expenses`

**Description:** Submit an expense with receipt photo for reimbursement.

**Path Parameters:**
- `driver_id` (UUID, required): The driver's ID

**Headers:**
```
Authorization: Bearer {token}
Content-Type: multipart/form-data
```

**Request Body (multipart/form-data):**
- `amount` (number, required): Expense amount (e.g., 45.50)
- `expense_type` (string, required): Type - "gas", "maintenance", "parking", "tolls", "other"
- `expense_date` (date, required): Date of expense (YYYY-MM-DD)
- `description` (string, required): Expense description
- `receipt_photo` (file, required): Receipt image (JPEG, PNG, PDF - max 10MB)

**Success Response (201):**
```json
{
  "id": "770e8400-e29b-41d4-a716-446655440002",
  "driver_id": "8f83da7b-7d21-4d49-891e-1ed75d411e4d",
  "amount": 45.50,
  "expense_type": "gas",
  "expense_date": "2026-02-16",
  "description": "Gas fill at Shell station",
  "receipt_url": "/uploads/receipts/8f83da7b_1708095000_abc123.jpg",
  "status": "pending",
  "manager_notes": null,
  "verified_amount": null,
  "resolved_at": null,
  "resolved_by": null,
  "pay_period_start": "2026-02-10",
  "pay_period_end": "2026-02-16",
  "created_at": "2026-02-16T18:30:00Z",
  "updated_at": "2026-02-16T18:30:00Z"
}
```

**Error Responses:**

*400 - Validation error:*
```json
{
  "detail": "Expense date cannot be in the future"
}
```

*400 - File too large:*
```json
{
  "detail": "File size exceeds 10MB limit"
}
```

*400 - Invalid file type:*
```json
{
  "detail": "Invalid file type. Only JPEG, PNG, and PDF are allowed"
}
```

**Frontend Example (React with File Upload):**
```javascript
const submitExpense = async (driverId, token, expenseData, receiptFile) => {
  const formData = new FormData();
  formData.append('amount', expenseData.amount);
  formData.append('expense_type', expenseData.expenseType);
  formData.append('expense_date', expenseData.date);
  formData.append('description', expenseData.description);
  formData.append('receipt_photo', receiptFile);

  try {
    const response = await axios.post(
      `${API_URL}/v1/drivers/${driverId}/expenses`,
      formData,
      {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'multipart/form-data'
        }
      }
    );

    return response.data;
  } catch (error) {
    console.error('Error submitting expense:', error);
    throw error;
  }
};

// Usage in component:
const handleSubmit = async (e) => {
  e.preventDefault();

  const expenseData = {
    amount: parseFloat(amount),
    expenseType: type,
    date: date, // YYYY-MM-DD format
    description: description
  };

  const file = e.target.receipt.files[0];

  try {
    const result = await submitExpense(driverId, token, expenseData, file);
    alert('Expense submitted successfully!');
  } catch (error) {
    alert('Failed to submit expense');
  }
};
```

**React Native Example (with Image Picker):**
```javascript
import * as ImagePicker from 'expo-image-picker';

const submitExpenseRN = async (driverId, token, expenseData) => {
  // Pick image
  const result = await ImagePicker.launchCameraAsync({
    mediaTypes: ImagePicker.MediaTypeOptions.Images,
    quality: 0.8,
  });

  if (result.canceled) return;

  const formData = new FormData();
  formData.append('amount', expenseData.amount);
  formData.append('expense_type', expenseData.expenseType);
  formData.append('expense_date', expenseData.date);
  formData.append('description', expenseData.description);

  // Add image
  formData.append('receipt_photo', {
    uri: result.assets[0].uri,
    type: 'image/jpeg',
    name: 'receipt.jpg'
  });

  try {
    const response = await fetch(
      `${API_URL}/v1/drivers/${driverId}/expenses`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'multipart/form-data',
        },
        body: formData
      }
    );

    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Error submitting expense:', error);
    throw error;
  }
};
```

**Complete UI Example (React Form):**
```jsx
function ExpenseForm({ driverId, token, onSuccess }) {
  const [amount, setAmount] = useState('');
  const [type, setType] = useState('gas');
  const [date, setDate] = useState(new Date().toISOString().split('T')[0]);
  const [description, setDescription] = useState('');
  const [receipt, setReceipt] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file && file.size > 10 * 1024 * 1024) {
      alert('File size must be less than 10MB');
      return;
    }
    setReceipt(file);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);

    try {
      const expenseData = {
        amount: parseFloat(amount),
        expenseType: type,
        date: date,
        description: description
      };

      await submitExpense(driverId, token, expenseData, receipt);

      // Reset form
      setAmount('');
      setDescription('');
      setReceipt(null);

      onSuccess?.();
      alert('Expense submitted successfully!');
    } catch (error) {
      alert('Failed to submit expense: ' + error.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <div>
        <label>Amount ($)</label>
        <input
          type="number"
          step="0.01"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          required
        />
      </div>

      <div>
        <label>Type</label>
        <select value={type} onChange={(e) => setType(e.target.value)} required>
          <option value="gas">Gas</option>
          <option value="maintenance">Maintenance</option>
          <option value="parking">Parking</option>
          <option value="tolls">Tolls</option>
          <option value="other">Other</option>
        </select>
      </div>

      <div>
        <label>Date</label>
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          max={new Date().toISOString().split('T')[0]}
          required
        />
      </div>

      <div>
        <label>Description</label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          required
        />
      </div>

      <div>
        <label>Receipt Photo</label>
        <input
          type="file"
          accept="image/jpeg,image/png,application/pdf"
          onChange={handleFileChange}
          required
        />
        {receipt && <p>Selected: {receipt.name}</p>}
      </div>

      <button type="submit" disabled={submitting}>
        {submitting ? 'Submitting...' : 'Submit Expense'}
      </button>
    </form>
  );
}
```

---

### 2. Get Expense History

**Endpoint:** `GET /v1/drivers/{driver_id}/expenses`

**Description:** Retrieves paginated expense history for the driver.

**Path Parameters:**
- `driver_id` (UUID, required): The driver's ID

**Query Parameters:**
- `page` (integer, optional, default: 1): Page number
- `page_size` (integer, optional, default: 10, max: 100): Items per page
- `status` (string, optional): Filter by status ("pending", "verified", "rejected")
- `expense_type` (string, optional): Filter by type ("gas", "maintenance", "parking", "tolls", "other")

**Headers:**
```
Authorization: Bearer {token}
```

**Success Response (200):**
```json
{
  "items": [
    {
      "id": "770e8400-e29b-41d4-a716-446655440002",
      "driver_id": "8f83da7b-7d21-4d49-891e-1ed75d411e4d",
      "amount": 45.50,
      "expense_type": "gas",
      "expense_date": "2026-02-16",
      "description": "Gas fill at Shell station",
      "receipt_url": "/uploads/receipts/8f83da7b_1708095000_abc123.jpg",
      "status": "verified",
      "manager_notes": "Approved",
      "verified_amount": 45.50,
      "resolved_at": "2026-02-17T10:00:00Z",
      "resolved_by": "manager-uuid",
      "pay_period_start": "2026-02-10",
      "pay_period_end": "2026-02-16",
      "created_at": "2026-02-16T18:30:00Z",
      "updated_at": "2026-02-17T10:00:00Z"
    }
  ],
  "total": 23,
  "page": 1,
  "page_size": 10,
  "total_pages": 3
}
```

**Frontend Example:**
```javascript
const getExpenseHistory = async (driverId, token, filters = {}) => {
  const params = new URLSearchParams({
    page: filters.page || 1,
    page_size: filters.pageSize || 10,
    ...(filters.status && { status: filters.status }),
    ...(filters.expenseType && { expense_type: filters.expenseType })
  });

  try {
    const response = await axios.get(
      `${API_URL}/v1/drivers/${driverId}/expenses?${params}`,
      {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      }
    );

    return response.data;
  } catch (error) {
    console.error('Error fetching expenses:', error);
    throw error;
  }
};
```

---

## Earnings View

### Get Driver Earnings

**Endpoint:** `GET /v1/drivers/{driver_id}/earnings`

**Description:** Retrieves detailed earnings breakdown for the driver with period-by-period calculations.

**Path Parameters:**
- `driver_id` (UUID, required): The driver's ID

**Query Parameters:**
- `page` (integer, optional, default: 1): Page number for periods
- `page_size` (integer, optional, default: 10, max: 50): Periods per page

**Headers:**
```
Authorization: Bearer {token}
```

**Success Response (200):**
```json
{
  "year_to_date": {
    "total_gross_earnings": 15240.00,
    "total_hours_worked": 1016.5,
    "total_days_worked": 127,
    "total_trips": 458,
    "total_expenses_reimbursed": 1250.75,
    "total_paid": 16490.75,
    "year": 2026
  },
  "current_period": {
    "period_start": "2026-02-10",
    "period_end": "2026-02-16",
    "gross_earnings": 720.00,
    "hours_worked": 48.0,
    "days_worked": 6,
    "trips_count": 24,
    "expenses_reimbursed": 85.50,
    "total_paid": 805.50,
    "pay_frequency": "weekly"
  },
  "periods": [
    {
      "period_start": "2026-02-10",
      "period_end": "2026-02-16",
      "gross_earnings": 720.00,
      "hours_worked": 48.0,
      "days_worked": 6,
      "trips_count": 24,
      "expenses_reimbursed": 85.50,
      "total_paid": 805.50,
      "status": "current"
    },
    {
      "period_start": "2026-02-03",
      "period_end": "2026-02-09",
      "gross_earnings": 840.00,
      "hours_worked": 56.0,
      "days_worked": 7,
      "trips_count": 32,
      "expenses_reimbursed": 120.00,
      "total_paid": 960.00,
      "status": "completed"
    }
  ],
  "total_periods": 18,
  "page": 1,
  "page_size": 10,
  "driver_info": {
    "pay_type": "hour",
    "pay_frequency": "weekly",
    "rate": 15.00
  }
}
```

**Frontend Example:**
```javascript
const getEarnings = async (driverId, token, page = 1) => {
  try {
    const response = await axios.get(
      `${API_URL}/v1/drivers/${driverId}/earnings?page=${page}&page_size=10`,
      {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      }
    );

    return response.data;
  } catch (error) {
    console.error('Error fetching earnings:', error);
    throw error;
  }
};
```

**Complete UI Example (React Dashboard):**
```jsx
function EarningsDashboard({ driverId, token }) {
  const [earnings, setEarnings] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchEarnings = async () => {
      try {
        const data = await getEarnings(driverId, token);
        setEarnings(data);
      } catch (error) {
        console.error(error);
      } finally {
        setLoading(false);
      }
    };

    fetchEarnings();
  }, [driverId, token]);

  if (loading) return <Spinner />;
  if (!earnings) return <div>No earnings data</div>;

  return (
    <div className="earnings-dashboard">
      {/* Year to Date Summary */}
      <div className="ytd-summary">
        <h2>Year to Date ({earnings.year_to_date.year})</h2>
        <div className="stats-grid">
          <div className="stat">
            <label>Total Gross Earnings</label>
            <span className="amount">${earnings.year_to_date.total_gross_earnings.toFixed(2)}</span>
          </div>
          <div className="stat">
            <label>Total Reimbursements</label>
            <span className="amount">${earnings.year_to_date.total_expenses_reimbursed.toFixed(2)}</span>
          </div>
          <div className="stat">
            <label>Total Paid</label>
            <span className="amount total">${earnings.year_to_date.total_paid.toFixed(2)}</span>
          </div>
          <div className="stat">
            <label>Hours Worked</label>
            <span>{earnings.year_to_date.total_hours_worked.toFixed(1)} hrs</span>
          </div>
          <div className="stat">
            <label>Days Worked</label>
            <span>{earnings.year_to_date.total_days_worked}</span>
          </div>
          <div className="stat">
            <label>Trips Completed</label>
            <span>{earnings.year_to_date.total_trips}</span>
          </div>
        </div>
      </div>

      {/* Current Period */}
      <div className="current-period">
        <h2>Current Period</h2>
        <p className="period-dates">
          {new Date(earnings.current_period.period_start).toLocaleDateString()} -
          {new Date(earnings.current_period.period_end).toLocaleDateString()}
        </p>
        <div className="stats-grid">
          <div className="stat">
            <label>Gross Earnings</label>
            <span className="amount">${earnings.current_period.gross_earnings.toFixed(2)}</span>
          </div>
          <div className="stat">
            <label>Reimbursements</label>
            <span className="amount">${earnings.current_period.expenses_reimbursed.toFixed(2)}</span>
          </div>
          <div className="stat">
            <label>Total</label>
            <span className="amount total">${earnings.current_period.total_paid.toFixed(2)}</span>
          </div>
        </div>
      </div>

      {/* Historical Periods */}
      <div className="periods-history">
        <h2>Period History</h2>
        <table>
          <thead>
            <tr>
              <th>Period</th>
              <th>Gross</th>
              <th>Reimbursements</th>
              <th>Total</th>
              <th>Hours</th>
              <th>Trips</th>
            </tr>
          </thead>
          <tbody>
            {earnings.periods.map((period, idx) => (
              <tr key={idx}>
                <td>
                  {new Date(period.period_start).toLocaleDateString()} -
                  {new Date(period.period_end).toLocaleDateString()}
                </td>
                <td>${period.gross_earnings.toFixed(2)}</td>
                <td>${period.expenses_reimbursed.toFixed(2)}</td>
                <td>${period.total_paid.toFixed(2)}</td>
                <td>{period.hours_worked.toFixed(1)}</td>
                <td>{period.trips_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

---

## Tax Information

### 1. Submit Tax Information (W-9)

**Endpoint:** `POST /v1/drivers/{driver_id}/tax-information`

**Description:** Submit W-9 tax information for 1099 generation. Can only be submitted once.

**Path Parameters:**
- `driver_id` (UUID, required): The driver's ID

**Headers:**
```
Authorization: Bearer {token}
Content-Type: multipart/form-data
```

**Request Body (multipart/form-data):**
- `tin_type` (string, required): "SSN" or "EIN"
- `tin` (string, required): Tax ID Number (format: XXX-XX-XXXX for SSN, XX-XXXXXXX for EIN)
- `legal_first_name` (string, required): Legal first name
- `legal_middle_name` (string, optional): Legal middle name
- `legal_last_name` (string, required): Legal last name
- `address_street` (string, required): Street address
- `address_city` (string, required): City
- `address_state` (string, required): State (2-letter code)
- `address_zip` (string, required): ZIP code
- `address_country` (string, required): Country (2-letter code, default: "US")
- `w9_document` (file, required): W-9 PDF document (max 5MB)

**Success Response (201):**
```json
{
  "id": "880e8400-e29b-41d4-a716-446655440003",
  "driver_id": "8f83da7b-7d21-4d49-891e-1ed75d411e4d",
  "tin_type": "SSN",
  "tin_masked": "***-**-4321",
  "legal_first_name": "John",
  "legal_middle_name": "Michael",
  "legal_last_name": "Doe",
  "address_street": "123 Main Street",
  "address_city": "Miami",
  "address_state": "FL",
  "address_zip": "33101",
  "address_country": "US",
  "w9_submitted": true,
  "w9_submitted_at": "2026-02-16T20:00:00Z",
  "w9_document_url": "/uploads/w9/8f83da7b_1708102800_w9.pdf",
  "created_at": "2026-02-16T20:00:00Z",
  "updated_at": "2026-02-16T20:00:00Z"
}
```

**Error Responses:**

*409 - Already submitted:*
```json
{
  "detail": "Tax information already exists for this driver"
}
```

*400 - Invalid TIN format:*
```json
{
  "detail": "Invalid TIN format. Expected: XXX-XX-XXXX"
}
```

**Frontend Example:**
```javascript
const submitTaxInfo = async (driverId, token, taxData, w9File) => {
  const formData = new FormData();
  formData.append('tin_type', taxData.tinType);
  formData.append('tin', taxData.tin);
  formData.append('legal_first_name', taxData.firstName);
  formData.append('legal_middle_name', taxData.middleName || '');
  formData.append('legal_last_name', taxData.lastName);
  formData.append('address_street', taxData.street);
  formData.append('address_city', taxData.city);
  formData.append('address_state', taxData.state);
  formData.append('address_zip', taxData.zip);
  formData.append('address_country', taxData.country || 'US');
  formData.append('w9_document', w9File);

  try {
    const response = await axios.post(
      `${API_URL}/v1/drivers/${driverId}/tax-information`,
      formData,
      {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'multipart/form-data'
        }
      }
    );

    return response.data;
  } catch (error) {
    if (error.response?.status === 409) {
      alert('Tax information already submitted!');
    }
    throw error;
  }
};
```

**UI Example (React Form):**
```jsx
function TaxInformationForm({ driverId, token, onSuccess }) {
  const [tinType, setTinType] = useState('SSN');
  const [tin, setTin] = useState('');
  const [firstName, setFirstName] = useState('');
  const [middleName, setMiddleName] = useState('');
  const [lastName, setLastName] = useState('');
  const [street, setStreet] = useState('');
  const [city, setCity] = useState('');
  const [state, setState] = useState('');
  const [zip, setZip] = useState('');
  const [w9File, setW9File] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const formatTIN = (value, type) => {
    const numbers = value.replace(/\D/g, '');

    if (type === 'SSN') {
      // Format: XXX-XX-XXXX
      if (numbers.length <= 3) return numbers;
      if (numbers.length <= 5) return `${numbers.slice(0, 3)}-${numbers.slice(3)}`;
      return `${numbers.slice(0, 3)}-${numbers.slice(3, 5)}-${numbers.slice(5, 9)}`;
    } else {
      // Format: XX-XXXXXXX
      if (numbers.length <= 2) return numbers;
      return `${numbers.slice(0, 2)}-${numbers.slice(2, 9)}`;
    }
  };

  const handleTinChange = (e) => {
    const formatted = formatTIN(e.target.value, tinType);
    setTin(formatted);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);

    try {
      const taxData = {
        tinType,
        tin,
        firstName,
        middleName,
        lastName,
        street,
        city,
        state,
        zip,
        country: 'US'
      };

      await submitTaxInfo(driverId, token, taxData, w9File);
      alert('Tax information submitted successfully!');
      onSuccess?.();
    } catch (error) {
      alert('Failed to submit: ' + error.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <div>
        <label>TIN Type</label>
        <select value={tinType} onChange={(e) => {
          setTinType(e.target.value);
          setTin('');
        }}>
          <option value="SSN">SSN</option>
          <option value="EIN">EIN</option>
        </select>
      </div>

      <div>
        <label>{tinType === 'SSN' ? 'SSN' : 'EIN'}</label>
        <input
          type="text"
          value={tin}
          onChange={handleTinChange}
          placeholder={tinType === 'SSN' ? 'XXX-XX-XXXX' : 'XX-XXXXXXX'}
          maxLength={tinType === 'SSN' ? 11 : 10}
          required
        />
      </div>

      <div>
        <label>Legal First Name</label>
        <input
          type="text"
          value={firstName}
          onChange={(e) => setFirstName(e.target.value)}
          required
        />
      </div>

      <div>
        <label>Legal Middle Name (optional)</label>
        <input
          type="text"
          value={middleName}
          onChange={(e) => setMiddleName(e.target.value)}
        />
      </div>

      <div>
        <label>Legal Last Name</label>
        <input
          type="text"
          value={lastName}
          onChange={(e) => setLastName(e.target.value)}
          required
        />
      </div>

      <div>
        <label>Street Address</label>
        <input
          type="text"
          value={street}
          onChange={(e) => setStreet(e.target.value)}
          required
        />
      </div>

      <div>
        <label>City</label>
        <input
          type="text"
          value={city}
          onChange={(e) => setCity(e.target.value)}
          required
        />
      </div>

      <div>
        <label>State</label>
        <input
          type="text"
          value={state}
          onChange={(e) => setState(e.target.value.toUpperCase())}
          maxLength={2}
          placeholder="FL"
          required
        />
      </div>

      <div>
        <label>ZIP Code</label>
        <input
          type="text"
          value={zip}
          onChange={(e) => setZip(e.target.value)}
          maxLength={10}
          required
        />
      </div>

      <div>
        <label>W-9 Document (PDF)</label>
        <input
          type="file"
          accept="application/pdf"
          onChange={(e) => setW9File(e.target.files[0])}
          required
        />
      </div>

      <button type="submit" disabled={submitting}>
        {submitting ? 'Submitting...' : 'Submit Tax Information'}
      </button>
    </form>
  );
}
```

---

### 2. Get 1099 Form

**Endpoint:** `GET /v1/drivers/{driver_id}/1099`

**Description:** Get 1099-NEC form data for a specific year. Requires W-9 to be submitted first.

**Path Parameters:**
- `driver_id` (UUID, required): The driver's ID

**Query Parameters:**
- `year` (integer, required): Tax year (e.g., 2026)

**Headers:**
```
Authorization: Bearer {token}
```

**Success Response (200):**
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
    "tin": "123-45-6789",
    "tin_type": "SSN",
    "tin_masked": "***-**-6789",
    "address": {
      "street": "123 Main Street",
      "city": "Miami",
      "state": "FL",
      "zip": "33101"
    }
  },
  "form_data": {
    "box_1_nonemployee_compensation": 15240.00,
    "box_2_payer_made_direct_sales": null,
    "box_4_federal_income_tax_withheld": 0.00,
    "box_5_state_tax_withheld": 0.00,
    "box_6_state_payers_state_no": null,
    "box_7_state_income": 15240.00
  },
  "earnings_breakdown": {
    "total_gross_earnings": 15240.00,
    "total_hours_worked": 1016.5,
    "total_days_worked": 127,
    "total_trips": 458,
    "pay_type": "hour",
    "rate": 15.00
  },
  "expenses_summary": {
    "total_expenses_reimbursed": 1250.75,
    "note": "Expenses are business reimbursements and not included in Box 1"
  },
  "payment_summary": {
    "total_gross_earnings": 15240.00,
    "total_expenses_reimbursed": 1250.75,
    "total_paid_to_driver": 16490.75,
    "total_reported_on_1099": 15240.00
  },
  "compliance": {
    "minimum_reporting_threshold": 600.00,
    "requires_1099": true,
    "form_due_date": "2027-01-31",
    "recipient_copy_due_date": "2027-01-31"
  }
}
```

**Error Responses:**

*400 - No tax info:*
```json
{
  "detail": "Tax information not found. Driver must complete W-9 first."
}
```

*400 - Below threshold:*
```json
{
  "detail": "Earnings below $600 threshold. 1099 not required. Total: $425.00"
}
```

**Frontend Example:**
```javascript
const get1099Form = async (driverId, token, year) => {
  try {
    const response = await axios.get(
      `${API_URL}/v1/drivers/${driverId}/1099?year=${year}`,
      {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      }
    );

    return response.data;
  } catch (error) {
    if (error.response?.status === 400) {
      alert(error.response.data.detail);
    }
    throw error;
  }
};
```

**UI Example (1099 Display):**
```jsx
function Form1099Display({ driverId, token }) {
  const [form1099, setForm1099] = useState(null);
  const [year, setYear] = useState(new Date().getFullYear() - 1);
  const [loading, setLoading] = useState(false);

  const fetchForm = async () => {
    setLoading(true);
    try {
      const data = await get1099Form(driverId, token, year);
      setForm1099(data);
    } catch (error) {
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchForm();
  }, [year]);

  if (loading) return <Spinner />;
  if (!form1099) return <div>No 1099 data available</div>;

  return (
    <div className="form-1099">
      <div className="form-header">
        <h2>Form 1099-NEC - Tax Year {form1099.tax_year}</h2>
        <select value={year} onChange={(e) => setYear(parseInt(e.target.value))}>
          {[...Array(3)].map((_, i) => {
            const y = new Date().getFullYear() - 1 - i;
            return <option key={y} value={y}>{y}</option>;
          })}
        </select>
      </div>

      <div className="payer-info">
        <h3>Payer Information</h3>
        <p>{form1099.payer.name}</p>
        <p>EIN: {form1099.payer.ein}</p>
        <p>{form1099.payer.address.street}</p>
        <p>{form1099.payer.address.city}, {form1099.payer.address.state} {form1099.payer.address.zip}</p>
      </div>

      <div className="recipient-info">
        <h3>Recipient Information</h3>
        <p>{form1099.recipient.name}</p>
        <p>{form1099.recipient.tin_type}: {form1099.recipient.tin_masked}</p>
        <p>{form1099.recipient.address.street}</p>
        <p>{form1099.recipient.address.city}, {form1099.recipient.address.state} {form1099.recipient.address.zip}</p>
      </div>

      <div className="form-boxes">
        <h3>Form 1099-NEC Boxes</h3>
        <div className="box">
          <label>Box 1: Nonemployee Compensation</label>
          <span className="amount">${form1099.form_data.box_1_nonemployee_compensation.toFixed(2)}</span>
        </div>
        <div className="box">
          <label>Box 4: Federal Income Tax Withheld</label>
          <span className="amount">${form1099.form_data.box_4_federal_income_tax_withheld.toFixed(2)}</span>
        </div>
      </div>

      <div className="breakdown">
        <h3>Earnings Breakdown</h3>
        <table>
          <tbody>
            <tr>
              <td>Total Gross Earnings (Reported on 1099)</td>
              <td>${form1099.earnings_breakdown.total_gross_earnings.toFixed(2)}</td>
            </tr>
            <tr>
              <td>Hours Worked</td>
              <td>{form1099.earnings_breakdown.total_hours_worked.toFixed(1)}</td>
            </tr>
            <tr>
              <td>Trips Completed</td>
              <td>{form1099.earnings_breakdown.total_trips}</td>
            </tr>
            <tr>
              <td>Expense Reimbursements (Not Taxable)</td>
              <td>${form1099.expenses_summary.total_expenses_reimbursed.toFixed(2)}</td>
            </tr>
            <tr className="total">
              <td><strong>Total Paid to You</strong></td>
              <td><strong>${form1099.payment_summary.total_paid_to_driver.toFixed(2)}</strong></td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="compliance-note">
        <p><small>Form due date: {new Date(form1099.compliance.form_due_date).toLocaleDateString()}</small></p>
        <p><small>Generated: {new Date(form1099.generated_at).toLocaleString()}</small></p>
      </div>
    </div>
  );
}
```

---

# 👨‍💼 MANAGER ENDPOINTS

## Shift Review

### 1. Get Shifts for Review

**Endpoint:** `GET /v1/managers/shifts/review`

**Description:** Get all shifts that need manager review (pending status or auto-closed).

**Query Parameters:**
- `page` (integer, optional, default: 1): Page number
- `page_size` (integer, optional, default: 20, max: 100): Items per page

**Headers:**
```
Authorization: Bearer {token}
```

**Success Response (200):**
```json
{
  "items": [
    {
      "id": "990e8400-e29b-41d4-a716-446655440004",
      "driver_id": "8f83da7b-7d21-4d49-891e-1ed75d411e4d",
      "driver_name": "John Doe",
      "started_at": "2026-02-16T08:00:00Z",
      "ended_at": "2026-02-16T20:15:00Z",
      "status": "completed",
      "review_status": "pending",
      "auto_closed": true,
      "hours_worked": 12.25,
      "manager_notes": null,
      "resolved_at": null,
      "resolved_by": null,
      "created_at": "2026-02-16T08:00:00Z",
      "updated_at": "2026-02-16T20:15:00Z"
    }
  ],
  "total": 5,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

**Frontend Example:**
```javascript
const getShiftsForReview = async (managerToken, page = 1) => {
  try {
    const response = await axios.get(
      `${API_URL}/v1/managers/shifts/review?page=${page}&page_size=20`,
      {
        headers: {
          'Authorization': `Bearer ${managerToken}`
        }
      }
    );

    return response.data;
  } catch (error) {
    console.error('Error fetching shifts for review:', error);
    throw error;
  }
};
```

---

### 2. Resolve Shift Review

**Endpoint:** `POST /v1/managers/shifts/{shift_id}/resolve`

**Description:** Approve, reject, or adjust a shift that needs review.

**Path Parameters:**
- `shift_id` (UUID, required): The shift's ID

**Headers:**
```
Authorization: Bearer {token}
Content-Type: application/json
```

**Request Body:**
```json
{
  "action": "approve",
  "manager_notes": "Verified with driver",
  "adjusted_start": null,
  "adjusted_end": null
}
```

**Body Parameters:**
- `action` (string, required): "approve", "reject", or "adjust"
- `manager_notes` (string, optional): Notes about the decision
- `adjusted_start` (datetime, optional): New start time (only for "adjust" action)
- `adjusted_end` (datetime, optional): New end time (only for "adjust" action)

**Success Response (200):**
```json
{
  "id": "990e8400-e29b-41d4-a716-446655440004",
  "driver_id": "8f83da7b-7d21-4d49-891e-1ed75d411e4d",
  "started_at": "2026-02-16T08:00:00Z",
  "ended_at": "2026-02-16T20:15:00Z",
  "status": "completed",
  "review_status": "approved",
  "auto_closed": true,
  "manager_notes": "Verified with driver",
  "resolved_at": "2026-02-17T09:00:00Z",
  "resolved_by": "manager-uuid",
  "created_at": "2026-02-16T08:00:00Z",
  "updated_at": "2026-02-17T09:00:00Z"
}
```

**Frontend Example:**
```javascript
const resolveShift = async (managerToken, shiftId, resolution) => {
  try {
    const response = await axios.post(
      `${API_URL}/v1/managers/shifts/${shiftId}/resolve`,
      resolution,
      {
        headers: {
          'Authorization': `Bearer ${managerToken}`,
          'Content-Type': 'application/json'
        }
      }
    );

    return response.data;
  } catch (error) {
    console.error('Error resolving shift:', error);
    throw error;
  }
};

// Usage examples:

// Approve shift
await resolveShift(token, shiftId, {
  action: 'approve',
  manager_notes: 'Looks good'
});

// Reject shift
await resolveShift(token, shiftId, {
  action: 'reject',
  manager_notes: 'Shift too long, please verify'
});

// Adjust shift times
await resolveShift(token, shiftId, {
  action: 'adjust',
  manager_notes: 'Adjusted end time based on last trip',
  adjusted_start: null, // keep original
  adjusted_end: '2026-02-16T18:30:00Z' // adjust end time
});
```

**UI Example (Manager Review Component):**
```jsx
function ShiftReviewCard({ shift, token, onResolved }) {
  const [notes, setNotes] = useState('');
  const [adjustedEnd, setAdjustedEnd] = useState('');
  const [resolving, setResolving] = useState(false);

  const handleResolve = async (action) => {
    setResolving(true);

    try {
      const resolution = {
        action,
        manager_notes: notes || undefined,
        ...(action === 'adjust' && adjustedEnd && {
          adjusted_end: new Date(adjustedEnd).toISOString()
        })
      };

      await resolveShift(token, shift.id, resolution);
      alert(`Shift ${action}d successfully`);
      onResolved?.();
    } catch (error) {
      alert('Failed to resolve shift');
    } finally {
      setResolving(false);
    }
  };

  const hours = shift.hours_worked || 0;
  const isAutoClosed = shift.auto_closed;

  return (
    <div className={`shift-card ${isAutoClosed ? 'auto-closed' : ''}`}>
      <div className="shift-header">
        <h3>{shift.driver_name}</h3>
        {isAutoClosed && <span className="badge">Auto-Closed</span>}
      </div>

      <div className="shift-details">
        <p>Started: {new Date(shift.started_at).toLocaleString()}</p>
        <p>Ended: {new Date(shift.ended_at).toLocaleString()}</p>
        <p>Hours: {hours.toFixed(2)}</p>
      </div>

      <div className="resolution-form">
        <textarea
          placeholder="Add notes (optional)"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />

        <div className="adjust-time">
          <label>Adjust End Time (optional)</label>
          <input
            type="datetime-local"
            value={adjustedEnd}
            onChange={(e) => setAdjustedEnd(e.target.value)}
          />
        </div>

        <div className="actions">
          <button
            onClick={() => handleResolve('approve')}
            disabled={resolving}
            className="btn-approve"
          >
            Approve
          </button>

          {adjustedEnd && (
            <button
              onClick={() => handleResolve('adjust')}
              disabled={resolving}
              className="btn-adjust"
            >
              Adjust & Approve
            </button>
          )}

          <button
            onClick={() => handleResolve('reject')}
            disabled={resolving}
            className="btn-reject"
          >
            Reject
          </button>
        </div>
      </div>
    </div>
  );
}
```

---

## Expense Review

### 1. Get Expenses for Review

**Endpoint:** `GET /v1/managers/expenses/review`

**Description:** Get all expenses pending manager verification.

**Query Parameters:**
- `page` (integer, optional, default: 1): Page number
- `page_size` (integer, optional, default: 20, max: 100): Items per page

**Headers:**
```
Authorization: Bearer {token}
```

**Success Response (200):**
```json
{
  "items": [
    {
      "id": "aa0e8400-e29b-41d4-a716-446655440005",
      "driver_id": "8f83da7b-7d21-4d49-891e-1ed75d411e4d",
      "driver_name": "John Doe",
      "amount": 45.50,
      "expense_type": "gas",
      "expense_date": "2026-02-16",
      "description": "Gas fill at Shell station",
      "receipt_url": "/uploads/receipts/8f83da7b_1708095000_abc123.jpg",
      "status": "pending",
      "manager_notes": null,
      "verified_amount": null,
      "resolved_at": null,
      "resolved_by": null,
      "created_at": "2026-02-16T18:30:00Z",
      "updated_at": "2026-02-16T18:30:00Z"
    }
  ],
  "total": 8,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

**Frontend Example:**
```javascript
const getExpensesForReview = async (managerToken, page = 1) => {
  try {
    const response = await axios.get(
      `${API_URL}/v1/managers/expenses/review?page=${page}&page_size=20`,
      {
        headers: {
          'Authorization': `Bearer ${managerToken}`
        }
      }
    );

    return response.data;
  } catch (error) {
    console.error('Error fetching expenses for review:', error);
    throw error;
  }
};
```

---

### 2. Resolve Expense Review

**Endpoint:** `POST /v1/managers/expenses/{expense_id}/resolve`

**Description:** Verify, reject, or adjust an expense.

**Path Parameters:**
- `expense_id` (UUID, required): The expense's ID

**Headers:**
```
Authorization: Bearer {token}
Content-Type: application/json
```

**Request Body:**
```json
{
  "action": "verify",
  "manager_notes": "Receipt verified",
  "adjusted_amount": null
}
```

**Body Parameters:**
- `action` (string, required): "verify", "reject", or "adjust"
- `manager_notes` (string, optional): Notes about the decision
- `adjusted_amount` (number, optional): Adjusted amount (only for "adjust" action)

**Success Response (200):**
```json
{
  "id": "aa0e8400-e29b-41d4-a716-446655440005",
  "driver_id": "8f83da7b-7d21-4d49-891e-1ed75d411e4d",
  "amount": 45.50,
  "expense_type": "gas",
  "expense_date": "2026-02-16",
  "description": "Gas fill at Shell station",
  "receipt_url": "/uploads/receipts/8f83da7b_1708095000_abc123.jpg",
  "status": "verified",
  "manager_notes": "Receipt verified",
  "verified_amount": 45.50,
  "resolved_at": "2026-02-17T09:15:00Z",
  "resolved_by": "manager-uuid",
  "created_at": "2026-02-16T18:30:00Z",
  "updated_at": "2026-02-17T09:15:00Z"
}
```

**Frontend Example:**
```javascript
const resolveExpense = async (managerToken, expenseId, resolution) => {
  try {
    const response = await axios.post(
      `${API_URL}/v1/managers/expenses/${expenseId}/resolve`,
      resolution,
      {
        headers: {
          'Authorization': `Bearer ${managerToken}`,
          'Content-Type': 'application/json'
        }
      }
    );

    return response.data;
  } catch (error) {
    console.error('Error resolving expense:', error);
    throw error;
  }
};

// Usage examples:

// Verify expense
await resolveExpense(token, expenseId, {
  action: 'verify',
  manager_notes: 'Receipt looks good'
});

// Reject expense
await resolveExpense(token, expenseId, {
  action: 'reject',
  manager_notes: 'Receipt not clear, please resubmit'
});

// Adjust amount
await resolveExpense(token, expenseId, {
  action: 'adjust',
  manager_notes: 'Approved partial amount based on receipt',
  adjusted_amount: 35.00
});
```

**UI Example (Expense Review Component):**
```jsx
function ExpenseReviewCard({ expense, token, onResolved }) {
  const [notes, setNotes] = useState('');
  const [adjustedAmount, setAdjustedAmount] = useState('');
  const [showReceipt, setShowReceipt] = useState(false);
  const [resolving, setResolving] = useState(false);

  const handleResolve = async (action) => {
    setResolving(true);

    try {
      const resolution = {
        action,
        manager_notes: notes || undefined,
        ...(action === 'adjust' && adjustedAmount && {
          adjusted_amount: parseFloat(adjustedAmount)
        })
      };

      await resolveExpense(token, expense.id, resolution);
      alert(`Expense ${action === 'verify' ? 'verified' : action}ed successfully`);
      onResolved?.();
    } catch (error) {
      alert('Failed to resolve expense');
    } finally {
      setResolving(false);
    }
  };

  return (
    <div className="expense-card">
      <div className="expense-header">
        <h3>{expense.driver_name}</h3>
        <span className="expense-type">{expense.expense_type}</span>
      </div>

      <div className="expense-details">
        <p><strong>Amount:</strong> ${expense.amount.toFixed(2)}</p>
        <p><strong>Date:</strong> {new Date(expense.expense_date).toLocaleDateString()}</p>
        <p><strong>Description:</strong> {expense.description}</p>
        <button onClick={() => setShowReceipt(true)}>View Receipt</button>
      </div>

      {showReceipt && (
        <div className="receipt-modal">
          <img src={`${API_URL}${expense.receipt_url}`} alt="Receipt" />
          <button onClick={() => setShowReceipt(false)}>Close</button>
        </div>
      )}

      <div className="resolution-form">
        <textarea
          placeholder="Add notes (optional)"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />

        <div className="adjust-amount">
          <label>Adjust Amount (optional)</label>
          <input
            type="number"
            step="0.01"
            value={adjustedAmount}
            onChange={(e) => setAdjustedAmount(e.target.value)}
            placeholder={expense.amount.toFixed(2)}
          />
        </div>

        <div className="actions">
          <button
            onClick={() => handleResolve('verify')}
            disabled={resolving}
            className="btn-verify"
          >
            Verify
          </button>

          {adjustedAmount && (
            <button
              onClick={() => handleResolve('adjust')}
              disabled={resolving}
              className="btn-adjust"
            >
              Adjust & Verify
            </button>
          )}

          <button
            onClick={() => handleResolve('reject')}
            disabled={resolving}
            className="btn-reject"
          >
            Reject
          </button>
        </div>
      </div>
    </div>
  );
}
```

---

## Driver Earnings View (Manager)

### Get Any Driver's Earnings

**Endpoint:** `GET /v1/managers/drivers/{driver_id}/earnings`

**Description:** View detailed earnings for any driver (manager access).

**Path Parameters:**
- `driver_id` (UUID, required): The driver's ID

**Query Parameters:**
- `page` (integer, optional, default: 1): Page number
- `page_size` (integer, optional, default: 10, max: 50): Periods per page

**Headers:**
```
Authorization: Bearer {token}
```

**Success Response (200):**
Same format as driver's earnings endpoint - see [Driver Earnings View](#earnings-view)

**Frontend Example:**
```javascript
const getDriverEarnings = async (managerToken, driverId, page = 1) => {
  try {
    const response = await axios.get(
      `${API_URL}/v1/managers/drivers/${driverId}/earnings?page=${page}`,
      {
        headers: {
          'Authorization': `Bearer ${managerToken}`
        }
      }
    );

    return response.data;
  } catch (error) {
    console.error('Error fetching driver earnings:', error);
    throw error;
  }
};
```

---

## 1099 Management

### 1. Get Bulk 1099 Data

**Endpoint:** `GET /v1/managers/1099/bulk`

**Description:** Get 1099 data for all eligible drivers for a tax year.

**Query Parameters:**
- `year` (integer, required): Tax year (e.g., 2026)
- `format` (string, optional, default: "json"): Response format ("json" or "csv")

**Headers:**
```
Authorization: Bearer {token}
```

**Success Response (200) - JSON format:**
```json
{
  "tax_year": 2026,
  "generated_at": "2027-01-15T10:00:00Z",
  "total_drivers": 45,
  "total_compensation": 685200.50,
  "drivers": [
    {
      "driver_id": "8f83da7b-7d21-4d49-891e-1ed75d411e4d",
      "driver_name": "John Doe",
      "tin_masked": "***-**-6789",
      "box_1_amount": 15240.00,
      "expenses_reimbursed": 1250.75,
      "total_paid": 16490.75,
      "has_tax_info": true
    },
    {
      "driver_id": "9f83da7b-7d21-4d49-891e-1ed75d411e4e",
      "driver_name": "Jane Smith",
      "tin_masked": "***-**-1234",
      "box_1_amount": 18600.00,
      "expenses_reimbursed": 1580.25,
      "total_paid": 20180.25,
      "has_tax_info": true
    }
  ]
}
```

**Success Response (200) - CSV format:**
```csv
driver_id,driver_name,tin_masked,box_1_amount,expenses_reimbursed,total_paid,has_tax_info
8f83da7b-7d21-4d49-891e-1ed75d411e4d,John Doe,***-**-6789,15240.00,1250.75,16490.75,true
9f83da7b-7d21-4d49-891e-1ed75d411e4e,Jane Smith,***-**-1234,18600.00,1580.25,20180.25,true
```

**Frontend Example:**
```javascript
const getBulk1099 = async (managerToken, year, format = 'json') => {
  try {
    const response = await axios.get(
      `${API_URL}/v1/managers/1099/bulk?year=${year}&format=${format}`,
      {
        headers: {
          'Authorization': `Bearer ${managerToken}`
        },
        ...(format === 'csv' && { responseType: 'blob' })
      }
    );

    if (format === 'csv') {
      // Download CSV file
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `1099_bulk_${year}.csv`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      return null;
    }

    return response.data;
  } catch (error) {
    console.error('Error fetching bulk 1099:', error);
    throw error;
  }
};
```

---

### 2. Download Bulk 1099 (CSV)

**Endpoint:** `GET /v1/managers/1099/bulk/download`

**Description:** Download 1099 data as CSV file.

**Query Parameters:**
- `year` (integer, required): Tax year

**Headers:**
```
Authorization: Bearer {token}
```

**Success Response (200):**
Returns CSV file with proper headers for download.

**Frontend Example:**
```javascript
const download1099CSV = async (managerToken, year) => {
  try {
    const response = await axios.get(
      `${API_URL}/v1/managers/1099/bulk/download?year=${year}`,
      {
        headers: {
          'Authorization': `Bearer ${managerToken}`
        },
        responseType: 'blob'
      }
    );

    // Create download link
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `1099_data_${year}.csv`);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  } catch (error) {
    console.error('Error downloading CSV:', error);
    throw error;
  }
};
```

---

### 3. Generate All 1099 PDFs

**Endpoint:** `POST /v1/managers/1099/generate-all`

**Description:** Generate PDF 1099 forms for all eligible drivers (async operation).

**Headers:**
```
Authorization: Bearer {token}
Content-Type: application/json
```

**Request Body:**
```json
{
  "year": 2026,
  "min_earnings": 600.00
}
```

**Body Parameters:**
- `year` (integer, required): Tax year
- `min_earnings` (number, optional, default: 600.00): Minimum earnings threshold

**Success Response (202):**
```json
{
  "message": "1099 PDF generation started",
  "job_id": "job-uuid",
  "total_drivers": 45,
  "estimated_completion": "2027-01-15T10:15:00Z"
}
```

**Note:** This is an async operation. The actual PDF generation happens in the background.

**Frontend Example:**
```javascript
const generateAll1099s = async (managerToken, year) => {
  try {
    const response = await axios.post(
      `${API_URL}/v1/managers/1099/generate-all`,
      { year, min_earnings: 600.00 },
      {
        headers: {
          'Authorization': `Bearer ${managerToken}`,
          'Content-Type': 'application/json'
        }
      }
    );

    alert(`PDF generation started for ${response.data.total_drivers} drivers`);
    return response.data;
  } catch (error) {
    console.error('Error generating 1099s:', error);
    throw error;
  }
};
```

**UI Example (Manager 1099 Dashboard):**
```jsx
function Manager1099Dashboard({ token }) {
  const [year, setYear] = useState(new Date().getFullYear() - 1);
  const [bulk1099, setBulk1099] = useState(null);
  const [loading, setLoading] = useState(false);

  const fetchBulk1099 = async () => {
    setLoading(true);
    try {
      const data = await getBulk1099(token, year);
      setBulk1099(data);
    } catch (error) {
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBulk1099();
  }, [year]);

  const handleDownloadCSV = async () => {
    await download1099CSV(token, year);
  };

  const handleGeneratePDFs = async () => {
    if (confirm(`Generate PDFs for all ${bulk1099?.total_drivers} drivers?`)) {
      await generateAll1099s(token, year);
    }
  };

  if (loading) return <Spinner />;

  return (
    <div className="manager-1099-dashboard">
      <div className="header">
        <h2>1099-NEC Management</h2>
        <select value={year} onChange={(e) => setYear(parseInt(e.target.value))}>
          {[...Array(5)].map((_, i) => {
            const y = new Date().getFullYear() - 1 - i;
            return <option key={y} value={y}>{y}</option>;
          })}
        </select>
      </div>

      {bulk1099 && (
        <>
          <div className="summary">
            <h3>Summary for {bulk1099.tax_year}</h3>
            <div className="stats">
              <div className="stat">
                <label>Total Drivers</label>
                <span>{bulk1099.total_drivers}</span>
              </div>
              <div className="stat">
                <label>Total Compensation</label>
                <span>${bulk1099.total_compensation.toFixed(2)}</span>
              </div>
            </div>
          </div>

          <div className="actions">
            <button onClick={handleDownloadCSV}>Download CSV</button>
            <button onClick={handleGeneratePDFs} className="primary">
              Generate All PDFs
            </button>
          </div>

          <div className="drivers-table">
            <table>
              <thead>
                <tr>
                  <th>Driver Name</th>
                  <th>TIN</th>
                  <th>Box 1 Amount</th>
                  <th>Reimbursements</th>
                  <th>Total Paid</th>
                  <th>Tax Info</th>
                </tr>
              </thead>
              <tbody>
                {bulk1099.drivers.map(driver => (
                  <tr key={driver.driver_id}>
                    <td>{driver.driver_name}</td>
                    <td>{driver.tin_masked}</td>
                    <td>${driver.box_1_amount.toFixed(2)}</td>
                    <td>${driver.expenses_reimbursed.toFixed(2)}</td>
                    <td>${driver.total_paid.toFixed(2)}</td>
                    <td>
                      {driver.has_tax_info ? (
                        <span className="badge success">Complete</span>
                      ) : (
                        <span className="badge warning">Missing</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
```

---

## 🚨 Error Handling

### Common Error Codes

All endpoints may return the following errors:

**401 Unauthorized:**
```json
{
  "detail": "Not authenticated"
}
```
*Solution:* Token is missing or invalid. Re-authenticate.

**403 Forbidden:**
```json
{
  "detail": "Not authorized to access this resource"
}
```
*Solution:* User doesn't have permission (e.g., driver trying to access manager endpoint).

**404 Not Found:**
```json
{
  "detail": "Resource not found"
}
```
*Solution:* The requested resource doesn't exist.

**422 Validation Error:**
```json
{
  "detail": [
    {
      "loc": ["body", "amount"],
      "msg": "value is not a valid float",
      "type": "type_error.float"
    }
  ]
}
```
*Solution:* Check request parameters and fix validation issues.

**500 Internal Server Error:**
```json
{
  "detail": "Internal server error"
}
```
*Solution:* Contact support if persistent.

### Global Error Handler Example

```javascript
// Axios interceptor for error handling
axios.interceptors.response.use(
  response => response,
  error => {
    const status = error.response?.status;

    switch (status) {
      case 401:
        // Redirect to login
        localStorage.removeItem('token');
        window.location.href = '/login';
        break;

      case 403:
        alert('You do not have permission to perform this action');
        break;

      case 404:
        alert('Resource not found');
        break;

      case 422:
        const errors = error.response.data.detail;
        if (Array.isArray(errors)) {
          const messages = errors.map(e => e.msg).join(', ');
          alert(`Validation error: ${messages}`);
        }
        break;

      case 500:
        alert('Server error. Please try again later.');
        break;

      default:
        alert('An error occurred');
    }

    return Promise.reject(error);
  }
);
```

---

## 📱 Frontend Examples

### Complete API Service Class

```javascript
class EarningsAPI {
  constructor(baseURL, token) {
    this.baseURL = baseURL;
    this.token = token;

    this.client = axios.create({
      baseURL: this.baseURL,
      headers: {
        'Authorization': `Bearer ${this.token}`
      }
    });
  }

  // DRIVER METHODS

  async startShift(driverId) {
    const { data } = await this.client.post(`/v1/drivers/${driverId}/shifts/start`, {});
    return data;
  }

  async endShift(driverId) {
    const { data } = await this.client.post(`/v1/drivers/${driverId}/shifts/end`, {});
    return data;
  }

  async getShiftHistory(driverId, page = 1, pageSize = 10, status = null) {
    const params = { page, page_size: pageSize };
    if (status) params.status = status;

    const { data } = await this.client.get(`/v1/drivers/${driverId}/shifts`, { params });
    return data;
  }

  async submitExpense(driverId, expenseData, receiptFile) {
    const formData = new FormData();
    Object.keys(expenseData).forEach(key => {
      formData.append(key, expenseData[key]);
    });
    formData.append('receipt_photo', receiptFile);

    const { data } = await this.client.post(
      `/v1/drivers/${driverId}/expenses`,
      formData,
      {
        headers: { 'Content-Type': 'multipart/form-data' }
      }
    );
    return data;
  }

  async getExpenseHistory(driverId, page = 1, pageSize = 10, filters = {}) {
    const params = { page, page_size: pageSize, ...filters };
    const { data } = await this.client.get(`/v1/drivers/${driverId}/expenses`, { params });
    return data;
  }

  async getEarnings(driverId, page = 1, pageSize = 10) {
    const { data } = await this.client.get(
      `/v1/drivers/${driverId}/earnings`,
      { params: { page, page_size: pageSize } }
    );
    return data;
  }

  async submitTaxInfo(driverId, taxData, w9File) {
    const formData = new FormData();
    Object.keys(taxData).forEach(key => {
      if (taxData[key]) formData.append(key, taxData[key]);
    });
    formData.append('w9_document', w9File);

    const { data } = await this.client.post(
      `/v1/drivers/${driverId}/tax-information`,
      formData,
      {
        headers: { 'Content-Type': 'multipart/form-data' }
      }
    );
    return data;
  }

  async get1099(driverId, year) {
    const { data } = await this.client.get(
      `/v1/drivers/${driverId}/1099`,
      { params: { year } }
    );
    return data;
  }

  // MANAGER METHODS

  async getShiftsForReview(page = 1, pageSize = 20) {
    const { data } = await this.client.get(
      '/v1/managers/shifts/review',
      { params: { page, page_size: pageSize } }
    );
    return data;
  }

  async resolveShift(shiftId, resolution) {
    const { data } = await this.client.post(
      `/v1/managers/shifts/${shiftId}/resolve`,
      resolution
    );
    return data;
  }

  async getExpensesForReview(page = 1, pageSize = 20) {
    const { data } = await this.client.get(
      '/v1/managers/expenses/review',
      { params: { page, page_size: pageSize } }
    );
    return data;
  }

  async resolveExpense(expenseId, resolution) {
    const { data } = await this.client.post(
      `/v1/managers/expenses/${expenseId}/resolve`,
      resolution
    );
    return data;
  }

  async getDriverEarnings(driverId, page = 1, pageSize = 10) {
    const { data } = await this.client.get(
      `/v1/managers/drivers/${driverId}/earnings`,
      { params: { page, page_size: pageSize } }
    );
    return data;
  }

  async getBulk1099(year, format = 'json') {
    const { data } = await this.client.get(
      '/v1/managers/1099/bulk',
      {
        params: { year, format },
        ...(format === 'csv' && { responseType: 'blob' })
      }
    );
    return data;
  }

  async download1099CSV(year) {
    const { data } = await this.client.get(
      '/v1/managers/1099/bulk/download',
      {
        params: { year },
        responseType: 'blob'
      }
    );

    // Auto-download
    const url = window.URL.createObjectURL(new Blob([data]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `1099_data_${year}.csv`);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  }

  async generateAll1099s(year, minEarnings = 600) {
    const { data } = await this.client.post(
      '/v1/managers/1099/generate-all',
      { year, min_earnings: minEarnings }
    );
    return data;
  }
}

// Usage:
const api = new EarningsAPI('http://localhost:8001', userToken);

// Driver usage
await api.startShift(driverId);
await api.submitExpense(driverId, expenseData, file);
const earnings = await api.getEarnings(driverId);

// Manager usage
const shiftsToReview = await api.getShiftsForReview();
await api.resolveShift(shiftId, { action: 'approve', manager_notes: 'OK' });
```

---

## 🎯 Best Practices

### 1. **Token Management**
- Store tokens securely (HttpOnly cookies preferred, or secure localStorage)
- Refresh tokens before they expire
- Clear tokens on logout
- Handle 401 errors globally by redirecting to login

### 2. **File Uploads**
- Validate file size on frontend before upload (max 10MB for receipts, 5MB for W-9)
- Validate file types (JPEG, PNG, PDF only)
- Show upload progress for better UX
- Compress images if possible

### 3. **Error Handling**
- Always use try/catch blocks
- Show user-friendly error messages
- Log errors for debugging
- Implement retry logic for network errors

### 4. **Performance**
- Use pagination for large lists
- Cache earnings data (but refresh periodically)
- Lazy load images (receipts)
- Debounce search/filter inputs

### 5. **UX Considerations**
- Show loading states during API calls
- Disable submit buttons while processing
- Provide clear success/error feedback
- Auto-refresh after mutations (shift end, expense submit, etc.)

---

## 📞 Support

For questions or issues with the Earnings API:
- See full API documentation: `docs/DRIVER_EARNINGS_SYSTEM_GUIDE.md`
- Contact: support@gt360.com
- Developer Slack: #earnings-api

---

**Last Updated:** February 16, 2026
**API Version:** 1.0
**Base URL:** `http://localhost:8001` (dev) | `https://api.gt360.com` (prod)
