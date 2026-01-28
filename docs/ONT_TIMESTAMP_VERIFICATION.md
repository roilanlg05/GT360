# ONT Location Timestamp Verification

**Verification Date:** 2026-01-27
**User Reported Time:** 23:16:44 CET
**DB Server Time:** 23:19:20 CET
**Location:** ONT (ID: `775af5fd-caf6-40c7-8236-d4728903d2d1`)

---

## ✅ CONFIRMATION: This is the SAME location you modified

---

## 📅 Complete Timeline (in CET - Central European Time)

| Time (CET)      | Event | Details | Minutes Ago |
|-----------------|-------|---------|-------------|
| **23:03:25** | Location Created | ONT location created | ~16 min |
| **23:03:45** | Step 1 Applied | Reduce filter (10 min), 18 trips affected | ~16 min |
| **23:03:58** | Step 2 Applied | Reduce filter (10 min), 18 trips affected | ~16 min |
| **23:04:00** | Step 3 Applied | Combine filter (5-15 gap), 8 trips affected | ~15 min |
| **23:04:33** | **REVERT Executed** | **Combine reverted, 18 trips updated** | **~15 min** |
| **23:16:44** | User Report Time | You provided this timestamp | ~3 min |
| **23:19:20** | Current Server Time | Database current time | now |

---

## 🎯 Current State

### Filter Steps (2026-02-28)

```
Step 1: Reduce (10 min) → Active: TRUE ✅ (should remain active)
Step 2: Reduce (10 min) → Active: TRUE ✅ (should remain active)
Step 3: Combine         → Active: FALSE ❌ (correctly reverted)
```

### Trips State (18 trips on Feb 28)

```
✅ Times ARE modified (reduced by 10 minutes)
✅ current_step_id points to Step 2 (d848c8b1-86f0-4b4d-8a17-a40ecc5a2aad)
✅ filtered_at = 2026-01-27 23:04:33 CET
❌ reduce_applied = FALSE (BUG - should be TRUE)
✅ combine_applied = FALSE (correct - was reverted)
```

---

## 🔍 Action Sequence Match

Your actions match the database timeline perfectly:

1. ✅ Created new ONT location (~23:03:25 CET)
2. ✅ Applied Reduce filter (~23:03:45 CET)
3. ✅ Applied Reduce filter again (~23:03:58 CET)
4. ✅ Applied Combine filter (~23:04:00 CET)
5. ✅ Reverted Combine filter (~23:04:33 CET)

**Time elapsed since last action:** ~15 minutes
**Matches your report:** YES ✅

---

## 🚨 Confirmed Bug

The revert operation:
- ✅ Correctly marked Step 3 (Combine) as inactive
- ✅ Correctly kept Steps 1 & 2 (Reduce) as active
- ✅ Correctly updated trip times (reduced by 10 minutes)
- ✅ Correctly set `current_step_id` to Step 2
- ❌ **FAILED to set `reduce_applied = TRUE`** (CRITICAL BUG)

This is 100% the location you modified, and the bug is confirmed in the backend revert process.

---

## 📊 Statistics

```
Location: 775af5fd-caf6-40c7-8236-d4728903d2d1
Airline: WN
Test Date: 2026-02-28

Total outbound scheduled trips: 461
Trips with modified times: 122 (26.5%)
Trips with reduce_applied flag: 0 (0%) ❌ BUG

Expected: 122 trips with reduce_applied = TRUE
Actual: 0 trips with reduce_applied = TRUE
```

---

## ✅ Conclusion

**This IS the correct location.** The timeline matches your actions exactly, occurring 15-16 minutes ago, which aligns with your report time of 23:16:44 CET.

The backend bug is confirmed: after reverting Combine, the Reduce filters remain active and modify trip times, but the `reduce_applied` flag is not being set.
