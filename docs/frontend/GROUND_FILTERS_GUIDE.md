# Ground Filters - Frontend Implementation Guide

## 🎯 Executive Summary

This guide explains how to properly classify and display ground-filtered trips in the GT360 application.

**Critical Fixes Required:**

1. **❌ WRONG Counter**: `➖ 0 (+461) | ⊡ 0 | ⤢ 0 (+60)`
   **✅ CORRECT Counter**: `➖ 150 | ⊡ 50 | ⤢ 30`

2. **Trip Classification**: Use boolean flags (`reduce_applied`, `combine_applied`, `expand_applied`)

3. **Icon Order**: Display icons LEFT to RIGHT in chronological order (order filters were applied)

4. **Display Format**: `{icons} {original_time} → {final_time}`
   - Example: `➖⤢ 04:45 → 04:25` (final time in orange)

---

## 📚 Table of Contents

1. [Filter Types & Icons](#1-filter-types--icons)
2. [Data Structures from Backend](#2-data-structures-from-backend)
3. [Valid Filter Combinations](#3-valid-filter-combinations)
4. [Display Format Specification](#4-display-format-specification)
5. [Counter Logic - CRITICAL FIX](#5-counter-logic---critical-fix)
6. [Classification Algorithm](#6-classification-algorithm)
7. [Preview vs Applied Display](#7-preview-vs-applied-display)
8. [Example Scenarios](#8-example-scenarios)
9. [API Endpoints Reference](#9-api-endpoints-reference)
10. [Visual Examples](#10-visual-examples)
11. [Common Pitfalls & Solutions](#11-common-pitfalls--solutions)

---

## 1. Filter Types & Icons

The GT360 ground filter system has **three filter types**:

| Filter Type | Icon | Color | Purpose |
|------------|------|-------|---------|
| **Reduce** | ➖ | Blue | Subtracts fixed minutes from pickup time |
| **Combine** | ⊡ | Purple | Moves pairs of trips to their midpoint when gap is within range |
| **Expand** | ⤢ | Orange | Spreads out chains of trips using accordion patterns |

### Icon Reference
```
Reduce:  ➖ (U+2796 Heavy Minus Sign) - Blue (#0066CC or similar)
Combine: ⊡ (U+22A1 Squared Dot Operator) - Purple (#9333EA or similar)
Expand:  ⤢ (U+2922 North East Arrow to Corner) - Orange (#F97316 or similar)
```

---

## 2. Data Structures from Backend

### 2.1 Trip Object Structure

Every trip object contains filter tracking fields:

```typescript
interface Trip {
  // Identification
  id: string;
  airline: string;
  flight_number: string;

  // Times
  pick_up_time: string;           // Current time after filters (HH:MM format)
  original_pick_up_time: string;  // IMMUTABLE: Original time before ANY filter

  // Filter Flags (use these for classification!)
  reduce_applied: boolean;        // True if Reduce was applied
  combine_applied: boolean;       // True if Combine was applied
  expand_applied: boolean;        // True if Expand was applied

  // Metadata
  filtered_at: string | null;     // ISO timestamp of last filter modification
  current_step_id: string | null; // UUID of last step that modified this trip

  // Other trip fields...
  pick_up_location: string;
  drop_off_location: string;
  hotel_name: string;
  // etc.
}
```

**Important**:
- `original_pick_up_time` is set once and never changes (immutable baseline)
- `pick_up_time` is the current time after all filters applied
- Filter flags can be combined (e.g., both `reduce_applied` and `expand_applied` can be true)

### 2.2 Preview Response (StepResult)

When previewing a filter step, the backend returns:

```typescript
interface StepResult {
  step_id: string | null;         // null for preview, UUID after apply
  filter_type: string;            // "reduce" | "combine" | "expand"
  pick_up_date: string;           // "YYYY-MM-DD"
  trips_modified: number;         // ⚠️ Count of NEW trips (don't use for counter!)
  changes: TripChange[];          // List of all time modifications
  exclusions: FilterExclusion[];  // Operations that were excluded
  summary: object;                // Summary stats
}

interface TripChange {
  trip_id: string;                // UUID of the trip
  original_time: string;          // Time BEFORE this modification
  new_time: string;               // Time AFTER modification
  filter_applied: string;         // "reduce" | "combine" | "expand"
  hotel_name: string;
  pick_up_date: string;
  airline: string;
  flight_number: string;
}

interface FilterExclusion {
  operation: string;              // e.g., "expand(A,B)" or "combine_skip"
  trip_ids: string[];
  reason: string;                 // Why was it excluded
  gap_before: number;
  gap_after: number;
}
```

**⚠️ CRITICAL**: `trips_modified` represents NEW trips affected, NOT total trips with filters!

### 2.3 Stack State Response

To determine icon order, fetch the filter stack state:

```typescript
interface StackState {
  location_id: string;
  airline: string;
  pick_up_date: string;
  steps: FilterStepInfo[];        // Ordered list of active steps
  total_trips_affected: number;   // Unique count of trips affected
}

interface FilterStepInfo {
  step_id: string;                // UUID of the step
  step_order: number;             // 1, 2, 3... ⭐ USE THIS FOR ICON ORDER!
  filter_type: string;            // "reduce" | "combine" | "expand"
  trips_affected: number;         // Count of trips this step modified
  windows: TimeWindow[];          // Filter configuration
  is_active: boolean;             // true = active, false = reverted
}

interface TimeWindow {
  start: string;                  // "HH:MM"
  end: string;                    // "HH:MM" or "24:00"
  enabled: boolean;

  // Configuration (depends on filter type)
  minutes_to_reduce?: number;     // For Reduce
  min_gap?: number;               // For Combine/Expand
  max_gap?: number;               // For Combine/Expand
  max_shift?: number;             // For Expand only
  hotel_names?: string[];         // Optional hotel filtering
}
```

**⭐ KEY**: Use `step_order` to determine chronological order of filter application!

### 2.4 How to Use These Structures

Complete workflow for displaying filtered trips:

```typescript
// 1. Fetch stack state to know filter application order
const stackState = await fetch(
  `/v2/locations/${locationId}/airlines/${airline}/filters/stack?pick_up_date=${date}`
).then(r => r.json());

// 2. Fetch trips (they already have filter flags set)
const trips = await fetch(
  `/v2/locations/${locationId}/airlines/${airline}/trips?pick_up_date=${date}`
).then(r => r.json());

// 3. Calculate counter breakdown
const counters = {
  reduce: trips.filter(t => t.reduce_applied).length,
  combine: trips.filter(t => t.combine_applied).length,
  expand: trips.filter(t => t.expand_applied).length
};

// 4. Display counter: "➖ 150 | ⊡ 50 | ⤢ 30"
const counterDisplay = `➖ ${counters.reduce} | ⊡ ${counters.combine} | ⤢ ${counters.expand}`;

// 5. For each trip, classify using the algorithm (see Section 6)
const classifiedTrips = trips.map(trip => classifyTrip(trip, stackState));
```

---

## 3. Valid Filter Combinations

Only **5 combinations** are valid. Combine and Expand are **mutually exclusive** (Rule A).

| # | Combination | Flags | Valid? |
|---|-------------|-------|--------|
| 1 | **Reduce only** | `reduce_applied=true` | ✅ Yes |
| 2 | **Combine only** | `combine_applied=true` | ✅ Yes |
| 3 | **Expand only** | `expand_applied=true` | ✅ Yes |
| 4 | **Reduce + Combine** | `reduce_applied=true, combine_applied=true` | ✅ Yes |
| 5 | **Reduce + Expand** | `reduce_applied=true, expand_applied=true` | ✅ Yes |
| 6 | Combine + Expand | `combine_applied=true, expand_applied=true` | ❌ **IMPOSSIBLE** |
| 7 | Reduce + Combine + Expand | All three true | ❌ **IMPOSSIBLE** |

### Why Combine + Expand Can't Coexist

**Regla de Mutua Exclusión**: El PRIMER filtro aplicado (según step_order) SIEMPRE GANA cuando hay conflicto.

**Razón**: Ambos Combine y Expand modifican el posicionamiento de trips y son mutuamente exclusivos por diseño:
- **Combine** mueve pares de trips a su punto medio
- **Expand** esparce cadenas de trips usando patrones de acordeón

**Comportamiento Exacto**:
1. **Si Combine se aplica primero (step_order=1)**:
   - Combine marca trips con `combine_applied=true`
   - Cuando Expand se ejecuta (step_order=2), FILTRA todos los trips con `combine_applied=true`
   - Resultado: Combine se mantiene, Expand NO toca esos trips

2. **Si Expand se aplica primero (step_order=1)**:
   - Expand marca trips con `expand_applied=true`
   - Cuando Combine se ejecuta (step_order=2), SALTA pares donde algún trip tiene `expand_applied=true`
   - Resultado: Expand se mantiene, Combine NO toca esos trips

**Implementación en código**:
- Combine verifica: `if trip.expand_applied: skip_pair()`
- Expand filtra: `available_trips = [t for t in trips if not t.combine_applied]`

**Documento completo**: Ver [COMBINE_EXPAND_RULES.md](COMBINE_EXPAND_RULES.md) para detalles técnicos completos.

---

## 4. Display Format Specification

### Base Template

```
{icons} {original_time} → {final_time}
```

- **Icons**: Displayed LEFT to RIGHT in chronological order (order filters were applied)
- **Original time**: Crossed out (strikethrough), gray color
- **Arrow**: `→` (U+2192 Rightwards Arrow), gray color
- **Final time**: Colored based on LAST filter applied

### Format for Each Combination

#### 1. Reduce Only
```
➖ 04:45 → 04:05
```
- Icons: `➖` (blue)
- Original: `04:45` (gray strikethrough)
- Final: `04:05` (blue)

#### 2. Combine Only
```
⊡ 04:45 → 04:35
```
- Icons: `⊡` (purple)
- Original: `04:45` (gray strikethrough)
- Final: `04:35` (purple)

#### 3. Expand Only
```
⤢ 04:45 → 04:25
```
- Icons: `⤢` (orange)
- Original: `04:45` (gray strikethrough)
- Final: `04:25` (orange)

#### 4. Reduce + Combine
```
➖⊡ 04:45 → 04:35
```
- Icons: `➖⊡` (reduce first/blue, then combine/purple)
- Original: `04:45` (gray strikethrough)
- Final: `04:35` (purple - last filter applied)

**Important**: If Combine was applied BEFORE Reduce (step_order determines this), show: `⊡➖`

#### 5. Reduce + Expand
```
➖⤢ 04:45 → 04:25
```
- Icons: `➖⤢` (reduce first/blue, then expand/orange)
- Original: `04:45` (gray strikethrough)
- Final: `04:25` (orange - last filter applied)

**Important**: If Expand was applied BEFORE Reduce, show: `⤢➖`

### Icon Order Rule

**⭐ CRITICAL**: Icons MUST be displayed in chronological order (left to right).

Use `stackState.steps[].step_order` to determine the order:

```typescript
// Example stack:
// Step 1 (order=1): Reduce
// Step 2 (order=2): Expand

// Trip has both reduce_applied=true and expand_applied=true
// Display icons: ➖⤢ (reduce first, then expand)

// If stack was:
// Step 1 (order=1): Expand
// Step 2 (order=2): Reduce

// Same trip would display: ⤢➖ (expand first, then reduce)
```

### Color Coding

| Element | Color Rule |
|---------|-----------|
| Original time | Gray with strikethrough |
| Arrow (→) | Gray |
| Final time | Color of the **LAST** filter applied |
| Icons | Each icon retains its own color (blue/purple/orange) |

**Last Filter Color**:
- If only Reduce: Blue
- If Combine applied last: Purple
- If Expand applied last: Orange

---

## 5. Counter Logic - CRITICAL FIX

### ❌ Current (Incorrect) Implementation

The preview counter currently shows:
```
➖ 0 (+461) | ⊡ 0 | ⤢ 0 (+60)
```

This is **WRONG** because:
1. Using `StepResult.trips_modified` which represents NEW trips only
2. Confusing format with `(+N)` notation
3. Showing all filter types even when count is 0

### ✅ Correct Implementation

**Display format**: `➖ {reduce_count} | ⊡ {combine_count} | ⤢ {expand_count}`

**Example**: `➖ 150 | ⊡ 50 | ⤢ 30`

### Implementation Code

```typescript
/**
 * Calculate filter counters for display
 * @param trips - Array of trip objects
 * @returns Counter breakdown by filter type
 */
function calculateFilterCounters(trips: Trip[]) {
  return {
    reduce: trips.filter(t => t.reduce_applied).length,
    combine: trips.filter(t => t.combine_applied).length,
    expand: trips.filter(t => t.expand_applied).length
  };
}

/**
 * Format counter display
 * @param counters - Counter object from calculateFilterCounters
 * @returns Formatted string for display
 */
function formatCounterDisplay(counters: { reduce: number; combine: number; expand: number }) {
  return `➖ ${counters.reduce} | ⊡ ${counters.combine} | ⤢ ${counters.expand}`;
}

// Usage:
const counters = calculateFilterCounters(trips);
const displayText = formatCounterDisplay(counters);
// Result: "➖ 150 | ⊡ 50 | ⤢ 30"
```

### Visual Representation

The counter should render with colored icons:

```
[➖ Blue icon] 150 | [⊡ Purple icon] 50 | [⤢ Orange icon] 30
```

Or in HTML:
```html
<div class="filter-counter">
  <span class="filter-item">
    <span class="icon blue">➖</span> 150
  </span>
  <span class="separator"> | </span>
  <span class="filter-item">
    <span class="icon purple">⊡</span> 50
  </span>
  <span class="separator"> | </span>
  <span class="filter-item">
    <span class="icon orange">⤢</span> 30
  </span>
</div>
```

### What NOT to Use

**❌ Don't use `StepResult.trips_modified`** for the counter:

```typescript
// ❌ WRONG - this is count of NEW trips affected by THIS filter
const wrongCounter = stepResult.trips_modified;

// ✅ CORRECT - count trips with filter flags set
const correctCounter = trips.filter(t => t.reduce_applied).length;
```

**Why?** `trips_modified` represents how many trips are being NEWLY affected by the current filter step. The counter should show ALL trips that currently have any filter applied, regardless of when it was applied.

---

## 6. Classification Algorithm

### Overview

To properly classify and display a trip:
1. Fetch the filter stack state to determine application order
2. Check which filters are applied to the trip (using boolean flags)
3. Build icon list in chronological order using `step_order`
4. Determine final time color (last filter applied)
5. Format display string

### Complete Implementation

```typescript
/**
 * Fetch filter stack state for a given location, airline, and date
 */
async function fetchStackState(
  locationId: string,
  airline: string,
  pickUpDate: string
): Promise<StackState> {
  const response = await fetch(
    `/v2/locations/${locationId}/airlines/${airline}/filters/stack?pick_up_date=${pickUpDate}`
  );
  return response.json();
}

/**
 * Classify a trip based on its filter flags and stack state
 * @param trip - The trip object
 * @param stackState - The filter stack state (for determining order)
 * @returns Classification object with icons, times, and colors
 */
function classifyTrip(trip: Trip, stackState: StackState) {
  // Build ordered list of filters based on stack
  const appliedFilters: Array<{ type: string; icon: string; color: string }> = [];

  // Sort steps by step_order to get chronological order
  const orderedSteps = [...stackState.steps].sort((a, b) => a.step_order - b.step_order);

  // Check which filters are applied to this trip, in chronological order
  for (const step of orderedSteps) {
    if (step.filter_type === 'reduce' && trip.reduce_applied) {
      appliedFilters.push({ type: 'reduce', icon: '➖', color: 'blue' });
    } else if (step.filter_type === 'combine' && trip.combine_applied) {
      appliedFilters.push({ type: 'combine', icon: '⊡', color: 'purple' });
    } else if (step.filter_type === 'expand' && trip.expand_applied) {
      appliedFilters.push({ type: 'expand', icon: '⤢', color: 'orange' });
    }
  }

  // Last filter determines final time color
  const finalTimeColor = appliedFilters.length > 0
    ? appliedFilters[appliedFilters.length - 1].color
    : 'blue'; // Default if no filters

  return {
    tripId: trip.id,
    icons: appliedFilters,
    originalTime: trip.original_pick_up_time,
    finalTime: trip.pick_up_time,
    finalTimeColor,
    displayText: formatDisplay(
      appliedFilters,
      trip.original_pick_up_time,
      trip.pick_up_time,
      finalTimeColor
    )
  };
}

/**
 * Format the display string for a classified trip
 */
function formatDisplay(
  icons: Array<{ icon: string; color: string }>,
  originalTime: string,
  finalTime: string,
  finalTimeColor: string
) {
  const iconString = icons.map(i => i.icon).join('');
  const originalFormatted = formatTime(originalTime); // e.g., "04:45"
  const finalFormatted = formatTime(finalTime);       // e.g., "04:05"

  return {
    icons: iconString,
    originalTime: originalFormatted,
    arrow: '→',
    finalTime: finalFormatted,
    finalTimeColor: finalTimeColor,
    // For display: `${iconString} ${originalFormatted} → ${finalFormatted}`
  };
}

/**
 * Format time string from HH:MM:SS to HH:MM
 */
function formatTime(time: string): string {
  if (!time) return '';
  // Handle both "HH:MM:SS" and "HH:MM" formats
  return time.substring(0, 5); // Returns "HH:MM"
}
```

### Usage Example

```typescript
// 1. Fetch stack state
const stackState = await fetchStackState(locationId, airline, '2026-01-31');

// Example stack state:
// stackState.steps = [
//   { step_id: 'uuid-1', step_order: 1, filter_type: 'reduce', ... },
//   { step_id: 'uuid-2', step_order: 2, filter_type: 'expand', ... }
// ]

// 2. Classify a trip
const trip = {
  id: 'trip-123',
  pick_up_time: '04:25',
  original_pick_up_time: '04:45',
  reduce_applied: true,
  combine_applied: false,
  expand_applied: true
};

const classification = classifyTrip(trip, stackState);

// Result:
// {
//   tripId: 'trip-123',
//   icons: [
//     { type: 'reduce', icon: '➖', color: 'blue' },
//     { type: 'expand', icon: '⤢', color: 'orange' }
//   ],
//   originalTime: '04:45',
//   finalTime: '04:25',
//   finalTimeColor: 'orange',
//   displayText: {
//     icons: '➖⤢',
//     originalTime: '04:45',
//     arrow: '→',
//     finalTime: '04:25',
//     finalTimeColor: 'orange'
//   }
// }

// 3. Display in UI: "➖⤢ 04:45 → 04:25" (final time in orange)
```

### React Component Example

```typescript
interface FilterDisplayProps {
  trip: Trip;
  stackState: StackState;
}

function FilterDisplay({ trip, stackState }: FilterDisplayProps) {
  const classification = classifyTrip(trip, stackState);

  if (classification.icons.length === 0) {
    // No filters applied
    return <span>{classification.originalTime}</span>;
  }

  return (
    <div className="filter-display">
      {/* Icons */}
      <span className="icons">
        {classification.icons.map((filter, idx) => (
          <span key={idx} className={`icon ${filter.color}`}>
            {filter.icon}
          </span>
        ))}
      </span>

      {/* Original time (strikethrough) */}
      <span className="original-time">{classification.originalTime}</span>

      {/* Arrow */}
      <span className="arrow">→</span>

      {/* Final time (colored) */}
      <span className={`final-time ${classification.finalTimeColor}`}>
        {classification.finalTime}
      </span>
    </div>
  );
}

// CSS:
// .original-time { text-decoration: line-through; color: gray; }
// .arrow { color: gray; }
// .final-time.blue { color: #0066CC; }
// .final-time.purple { color: #9333EA; }
// .final-time.orange { color: #F97316; }
```

---

## 7. Preview vs Applied Display

### Preview State (Before Applying)

**Purpose**: Show what WILL happen if the filter is applied

**What to Display**:
- **ALL filtered trips**: Both existing filtered trips AND trips being newly modified
- Use `StepResult.changes[]` to get proposed modifications
- Counter shows breakdown by filter type (current state)
- Format same as applied state

**Implementation**:
```typescript
async function showPreview(locationId: string, airline: string, config: FilterConfig) {
  // 1. Preview the step
  const previewResult = await fetch('/v2/.../filters/step/preview', {
    method: 'POST',
    body: JSON.stringify(config)
  }).then(r => r.json());

  // 2. Fetch current trips to get filter flags
  const trips = await fetchTrips(locationId, airline, config.pick_up_date);

  // 3. Fetch stack state for icon ordering
  const stackState = await fetchStackState(locationId, airline, config.pick_up_date);

  // 4. Calculate counter (CURRENT state, not preview!)
  const counters = calculateFilterCounters(trips);

  // 5. Display:
  // - Header: "Trips with filters applied"
  // - Counter: "➖ 150 | ⊡ 50 | ⤢ 30"
  // - Section: "Proposed Changes (${previewResult.changes.length})"
  // - List all trips that will be modified
}
```

**Preview Dialog Structure**:
```
┌────────────────────────────────────────────┐
│ Preview Changes                        [X] │
│ Review changes before applying             │
├────────────────────────────────────────────┤
│ Trips with filters applied                 │
│ ➖ 150 | ⊡ 50 | ⤢ 30                        │
├────────────────────────────────────────────┤
│ Proposed Changes (461)                     │
│                                            │
│ [List of all trips that will be modified] │
│                                            │
│ [Apply Changes] [Cancel]                   │
└────────────────────────────────────────────┘
```

### Applied State (After Applying)

**Purpose**: Show trips with filters actually applied

**What to Display**:
- Trips with filter flags set to true
- Use trip's `reduce_applied`, `combine_applied`, `expand_applied` flags
- Display original → final time using classification algorithm
- Icons in chronological order (left to right)

**Implementation**:
```typescript
async function showAppliedTrips(locationId: string, airline: string, pickUpDate: string) {
  // 1. Fetch trips
  const trips = await fetchTrips(locationId, airline, pickUpDate);

  // 2. Fetch stack state for icon ordering
  const stackState = await fetchStackState(locationId, airline, pickUpDate);

  // 3. Filter trips that have any filter applied
  const filteredTrips = trips.filter(t =>
    t.reduce_applied || t.combine_applied || t.expand_applied
  );

  // 4. Classify each trip
  const classifiedTrips = filteredTrips.map(trip => ({
    ...trip,
    classification: classifyTrip(trip, stackState)
  }));

  // 5. Display in "Ground Filters" column
  return classifiedTrips;
}
```

**Key Differences**:

| Aspect | Preview | Applied |
|--------|---------|---------|
| **Data source** | `StepResult.changes[]` | Trip records with flags |
| **Counter** | Current state (before applying) | Current state (after applying) |
| **Trip list** | All trips that will be modified | All trips with filters applied |
| **Purpose** | Show proposed changes | Show actual state |

---

## 8. Example Scenarios

### Scenario 1: Single Reduce Filter

**Trip Data**:
```json
{
  "id": "trip-123",
  "pick_up_time": "04:05",
  "original_pick_up_time": "04:45",
  "reduce_applied": true,
  "combine_applied": false,
  "expand_applied": false
}
```

**Display**:
- Icons: `➖` (blue)
- Time: `04:45 → 04:05`
- Final time color: Blue
- Full display: `➖ 04:45 → 04:05`

### Scenario 2: Reduce + Expand

**Trip Data**:
```json
{
  "id": "trip-456",
  "pick_up_time": "04:25",
  "original_pick_up_time": "04:45",
  "reduce_applied": true,
  "combine_applied": false,
  "expand_applied": true
}
```

**Stack State**:
```json
{
  "steps": [
    { "step_order": 1, "filter_type": "reduce" },
    { "step_order": 2, "filter_type": "expand" }
  ]
}
```

**Display**:
- Icons: `➖⤢` (reduce first, then expand)
- Time: `04:45 → 04:25`
- Final time color: Orange (last filter = expand)
- Full display: `➖⤢ 04:45 → 04:25`

### Scenario 3: Preview Counter Calculation

**Current Trips State**:
```typescript
const trips = [
  // 100 trips with only reduce
  { reduce_applied: true, combine_applied: false, expand_applied: false },

  // 50 trips with reduce + combine
  { reduce_applied: true, combine_applied: true, expand_applied: false },

  // 30 trips with only expand
  { reduce_applied: false, combine_applied: false, expand_applied: true },

  // 281 trips with no filters
  { reduce_applied: false, combine_applied: false, expand_applied: false }
];
// Total: 461 trips
```

**Counter Calculation**:
```typescript
const counters = {
  reduce: 100 + 50 = 150,     // Trips with reduce_applied=true
  combine: 50,                 // Trips with combine_applied=true
  expand: 30                   // Trips with expand_applied=true
};
```

**✅ CORRECT Display**: `➖ 150 | ⊡ 50 | ⤢ 30`

**❌ WRONG Displays**:
- `0 (+461)` ← Using trips_modified incorrectly
- `➖ 0 (+461) | ⊡ 0 | ⤢ 0 (+60)` ← Confusing format with +N notation
- `180 trips filtered` ← Missing breakdown by type

### Scenario 4: Combine Applied Before Reduce

**Trip Data**:
```json
{
  "id": "trip-789",
  "pick_up_time": "04:30",
  "original_pick_up_time": "04:45",
  "reduce_applied": true,
  "combine_applied": true,
  "expand_applied": false
}
```

**Stack State** (Combine applied first):
```json
{
  "steps": [
    { "step_order": 1, "filter_type": "combine" },
    { "step_order": 2, "filter_type": "reduce" }
  ]
}
```

**Display**:
- Icons: `⊡➖` (combine first, then reduce)
- Time: `04:45 → 04:30`
- Final time color: Blue (last filter = reduce)
- Full display: `⊡➖ 04:45 → 04:30`

**Note**: Icon order depends on `step_order`, not filter type!

### Scenario 5: No Filters Applied

**Trip Data**:
```json
{
  "id": "trip-999",
  "pick_up_time": "05:00",
  "original_pick_up_time": "05:00",
  "reduce_applied": false,
  "combine_applied": false,
  "expand_applied": false
}
```

**Display**:
- No icons
- Just show time: `05:00`
- No arrow or original time (since they're the same)

---

## 9. API Endpoints Reference

### Filter Stack Endpoints

#### Get Stack State
```
GET /v2/locations/{location_id}/airlines/{airline}/filters/stack
Query params: pick_up_date (YYYY-MM-DD)
```
Returns: `StackState` with all active filter steps

#### Preview Filter Step
```
POST /v2/locations/{location_id}/airlines/{airline}/filters/step/preview
Body: FilterStepConfig
```
Returns: `StepResult` with proposed changes (step_id will be null)

#### Apply Filter Step
```
POST /v2/locations/{location_id}/airlines/{airline}/filters/step/apply
Body: FilterStepConfig
```
Returns: `StepResult` with applied changes (step_id will be UUID)

#### Revert Last Step
```
POST /v2/locations/{location_id}/airlines/{airline}/filters/revert-last
Query params: pick_up_date (YYYY-MM-DD)
```
Returns: Revert result with updated stack state

#### Revert Specific Step
```
POST /v2/locations/{location_id}/airlines/{airline}/filters/step/{step_id}/revert
```
Returns: Revert result with updated stack state

### Bulk Operations

#### Bulk Preview
```
POST /v2/locations/{location_id}/airlines/{airline}/filters/bulk/preview
Body: { start_date, end_date, config }
```
Returns: Array of `StepResult` for each date

#### Bulk Apply
```
POST /v2/locations/{location_id}/airlines/{airline}/filters/bulk/apply
Body: { start_date, end_date, config }
```
Returns: Array of `StepResult` for each date

#### Bulk Revert
```
POST /v2/locations/{location_id}/airlines/{airline}/filters/bulk/revert
Body: { start_date, end_date, step_order? }
```
Returns: Array of revert results

### Example Request

```typescript
// Preview a reduce filter
const response = await fetch(
  '/v2/locations/uuid-123/airlines/WN/filters/step/preview',
  {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      filter_type: 'reduce',
      pick_up_date: '2026-01-31',
      windows: [
        {
          start: '05:00',
          end: '10:00',
          enabled: true,
          minutes_to_reduce: 15
        }
      ]
    })
  }
);

const stepResult = await response.json();
// stepResult.changes contains all proposed time modifications
```

---

## 10. Visual Examples

### Ground Filters Column (List View)

Based on the provided screenshots, the corrected display:

```
┌─────────────┬──────────┬─────────────────────────────┐
│ Types       │ Date     │ Ground Filters              │
├─────────────┼──────────┼─────────────────────────────┤
│ ✈️ Outbound │ Jan 31   │ ➖ 04:45 → 04:05            │
│ ✈️ Outbound │ Jan 31   │ ➖⤢ 04:45 → 04:25           │
│ ✈️ Outbound │ Jan 31   │ ➖ 04:45 → 04:35            │
│ ✈️ Outbound │ Jan 31   │ ➖ 04:55 → 04:45            │
│ ✈️ Outbound │ Jan 31   │ ➖ 05:05 → 04:55            │
│ ✈️ Outbound │ Jan 31   │ ➖⤢ 05:05 → 05:05           │
│ ✈️ Outbound │ Jan 31   │ ➖ 05:50 → 05:40            │
│ ✈️ Outbound │ Jan 31   │ ➖ 06:30 → 06:20            │
└─────────────┴──────────┴─────────────────────────────┘
```

**Key Points**:
- Icons shown in chronological order
- Original time crossed out (gray strikethrough)
- Final time colored based on last filter
- Clean, consistent format

### Preview Changes Dialog

```
┌──────────────────────────────────────────────────────────┐
│ Preview Changes                                      [X] │
│ Review changes before applying                           │
├──────────────────────────────────────────────────────────┤
│ Trips with filters applied                               │
│                                                           │
│ ➖ 150 | ⊡ 50 | ⤢ 30                                      │
│ (current filter breakdown)                               │
├──────────────────────────────────────────────────────────┤
│ Proposed Changes (461)                                   │
│                                                           │
│ 📅 Sat, Jan 31                            13 changes     │
├──────────────────────────────────────────────────────────┤
│ WN 3023                                 ➖ 04:45 → 04:05 │
│ Marriott Riverside at the Convention Center              │
├──────────────────────────────────────────────────────────┤
│ WN 4667                                 ➖ 04:45 → 04:35 │
│ Marriott Riverside at the Convention Center              │
├──────────────────────────────────────────────────────────┤
│ WN 4667  Mission Inn Hotel              ➖ 04:45 → 04:35 │
├──────────────────────────────────────────────────────────┤
│ WN 2220  Mission Inn Hotel              ➖ 04:55 → 04:45 │
├──────────────────────────────────────────────────────────┤
│ WN 3034                                 ➖ 05:05 → 04:55 │
│ Marriott Riverside at the Convention Center              │
├──────────────────────────────────────────────────────────┤
│ WN 3034  Mission Inn Hotel              ➖ 05:05 → 04:55 │
├──────────────────────────────────────────────────────────┤
│ WN 1992  Mission Inn Hotel              ➖ 05:50 → 05:40 │
├──────────────────────────────────────────────────────────┤
│                                                           │
│ 461 trips will be modified                               │
│                                                           │
│ [Apply Changes]  [Cancel]                                │
└──────────────────────────────────────────────────────────┘
```

**Header Section**:
- Shows current filter breakdown: `➖ 150 | ⊡ 50 | ⤢ 30`
- NOT using trips_modified from preview result
- Uses actual trip filter flags

**Trip List**:
- Shows all trips that will be modified
- Each trip displays icons + time change
- Icons in chronological order

### Color Coding Reference

| Element | Color | CSS Example |
|---------|-------|-------------|
| Original time | Gray strikethrough | `color: #6B7280; text-decoration: line-through;` |
| Arrow (→) | Gray | `color: #6B7280;` |
| Final time (Reduce) | Blue | `color: #0066CC;` |
| Final time (Combine) | Purple | `color: #9333EA;` |
| Final time (Expand) | Orange | `color: #F97316;` |
| Reduce icon (➖) | Blue | `color: #0066CC;` |
| Combine icon (⊡) | Purple | `color: #9333EA;` |
| Expand icon (⤢) | Orange | `color: #F97316;` |

---

## 11. Common Pitfalls & Solutions

### Pitfall 1: Using `trips_modified` for Counter

**❌ WRONG**:
```typescript
// Using StepResult.trips_modified
const counter = stepResult.trips_modified;
// This is count of NEW trips affected, not total!
```

**✅ CORRECT**:
```typescript
// Count trips with filter flags set
const counters = {
  reduce: trips.filter(t => t.reduce_applied).length,
  combine: trips.filter(t => t.combine_applied).length,
  expand: trips.filter(t => t.expand_applied).length
};
```

**Why?** `trips_modified` represents how many ADDITIONAL trips are being affected by the current filter, not the total count of filtered trips.

### Pitfall 2: Not Preserving Icon Order

**❌ WRONG**:
```typescript
// Always showing reduce first
if (trip.reduce_applied) icons.push('➖');
if (trip.combine_applied) icons.push('⊡');
if (trip.expand_applied) icons.push('⤢');
// This ignores chronological order!
```

**✅ CORRECT**:
```typescript
// Use step_order from stack state
const orderedSteps = stackState.steps.sort((a, b) => a.step_order - b.step_order);
for (const step of orderedSteps) {
  if (step.filter_type === 'reduce' && trip.reduce_applied) {
    icons.push({ icon: '➖', color: 'blue' });
  }
  // etc.
}
```

**Why?** Filters can be applied in any order. Icon order must reflect chronological application order using `step_order`.

### Pitfall 3: Assuming Combine + Expand is Valid

**❌ WRONG**:
```typescript
// Allowing both flags
if (trip.combine_applied && trip.expand_applied) {
  // This should NEVER happen!
}
```

**✅ CORRECT**:
```typescript
// These are mutually exclusive
if (trip.combine_applied && trip.expand_applied) {
  console.error('Invalid state: Combine and Expand cannot both be true!');
  // Handle error or log warning
}
```

**Why?** The backend enforces Rule A: Combine and Expand are mutually exclusive. If you see both flags true, it's a data integrity issue.

### Pitfall 4: Showing Confusing Counter Format

**❌ WRONG**:
```typescript
// Confusing +N notation
const display = `➖ ${existingCount} (+${newCount})`;
// Result: "➖ 0 (+461)" - What does this mean?
```

**✅ CORRECT**:
```typescript
// Simple breakdown by type
const display = `➖ ${reduceCount} | ⊡ ${combineCount} | ⤢ ${expandCount}`;
// Result: "➖ 150 | ⊡ 50 | ⤢ 30" - Clear and informative
```

**Why?** The `(+N)` format is ambiguous. Users don't need to see "new" vs "existing" - they just need the current total by filter type.

### Pitfall 5: Not Handling Edge Cases

**❌ WRONG**:
```typescript
// Assuming original_pick_up_time always exists
const display = `${trip.original_pick_up_time} → ${trip.pick_up_time}`;
```

**✅ CORRECT**:
```typescript
// Handle missing original time
const originalTime = trip.original_pick_up_time || trip.pick_up_time;
const display = `${originalTime} → ${trip.pick_up_time}`;

// Or don't show arrow if times are the same
if (originalTime === trip.pick_up_time) {
  return <span>{trip.pick_up_time}</span>;
}
```

**Why?** Trips without filters won't have `original_pick_up_time` set. Handle this gracefully.

### Pitfall 6: Forgetting to Fetch Stack State

**❌ WRONG**:
```typescript
// Classifying without stack state
const classification = classifyTrip(trip); // Missing stackState!
```

**✅ CORRECT**:
```typescript
// Always fetch stack state first
const stackState = await fetchStackState(locationId, airline, pickUpDate);
const classification = classifyTrip(trip, stackState);
```

**Why?** You need stack state to determine chronological order of filters using `step_order`.

---

## 🎓 Summary Checklist

Use this checklist to verify your implementation:

### Counter Display
- [ ] Counter shows breakdown by filter type: `➖ {n} | ⊡ {n} | ⤢ {n}`
- [ ] Counter uses trip filter flags, NOT `trips_modified`
- [ ] Icons are colored (blue, purple, orange)
- [ ] No confusing `(+N)` notation

### Trip Classification
- [ ] Icons displayed in chronological order (left to right)
- [ ] Using `step_order` from stack state to determine order
- [ ] Final time color matches LAST filter applied
- [ ] Format: `{icons} {original_time} → {final_time}`

### Filter Combinations
- [ ] Only 5 valid combinations implemented
- [ ] Handling Combine + Expand as impossible/error case
- [ ] Using boolean flags: `reduce_applied`, `combine_applied`, `expand_applied`

### Data Handling
- [ ] Fetching stack state via API for icon ordering
- [ ] Using trip's `original_pick_up_time` and `pick_up_time` fields
- [ ] Handling edge cases (no filters, missing original time)

### Preview vs Applied
- [ ] Preview shows ALL filtered trips (existing + new)
- [ ] Counter shows current state, not preview state
- [ ] Applied state uses trip filter flags directly

---

## 📞 Support

If you have questions about this implementation:

1. **Backend Team**: Contact for API changes or data structure questions
2. **Product Team**: Contact for UX/design clarifications
3. **Reference Files**:
   - Backend models: `/features/trips/models/filter_models.py`
   - Trip schema: `/shared/db/schemas/trips/trips.py`
   - Core logic: `/features/trips/services/step_filter_service.py`

---

**Last Updated**: 2026-01-31
**Version**: 1.0
