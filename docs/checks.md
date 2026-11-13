# Data Quality Checks — harga-pangan-dq

## Overview

M3 introduces **seven data quality checks** that run after ingestion and loading, recording incidents in an append-only event log. Critical incidents that cannot be auto-resolved are opened as GitHub Issues.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     hpdq check (M3)                              │
├─────────────────────────────────────────────────────────────────┤
│  1. Freshness     → 2. Completeness → 3. Validity               │
│  4. Duplicates    → 5. Schema drift → 6. Anomaly                │
│  7. Reconciliation                                           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                    Incident events (SQLite)
                              ↓
                    Critical → GitHub Issue
```

## The Seven Checks

### 1. Freshness & Stale Re-delivery

**What it checks:**
- The national row for today exists by 14:00 WIB
- Volatile commodities don't show stale re-delivery (>99.5th percentile unchanged)

**Severity:**
- Warning: missing by 17:00 WIB
- Critical: missing after 17:00 WIB or high stale share

**Incident scope:** `commodity_date` (national row missing)

---

### 2. Completeness

**What it checks:**
- Every expected `(commodity, province)` combination is reported
- Expected set = combinations that reported on ≥80% of the last 40 business days

**Severity:**
- Warning: completeness < 80% before 17:00 WIB
- Critical: whole province missing or < 80% after 17:00 WIB

**Incident scope:** `province` (whole province missing) or `commodity_date` (low completeness)

---

### 3. Validity

**What it checks:**
- Price parses to integer > 0
- Price lies within plausible range (seeded, wide margin)
- Unit matches expected unit

**Severity:**
- Critical for all (cell-level quarantine)

**Incident scope:**
- `cell`: parse error or out of range
- `commodity_date`: unit mismatch

---

### 4. Duplicates

**What it checks:**
- `(commodity, area, date)` is unique within a snapshot

**Severity:**
- Warning: identical duplicates (deduped)
- Critical: conflicting duplicates (commodity-day quarantined)

**Incident scope:** `cell` (identical) or `commodity_date` (conflicting)

---

### 5. Schema Drift

**What it checks:**
- Response fingerprint matches versioned contract
- Top-level keys, row keys, date format, level values, number format, commodity/province lists

**Severity:**
- Critical (parser refuses unknown shapes)

**Incident scope:** `snapshot`

---

### 6. Anomaly

**What it checks:**
- Detects real price shocks vs data errors using:
  - Robust z-score over trailing 60 observations (MAD floor)
  - Gap widening for breaks (√gap)
  - Decimal signature (×10, ×1000)
  - Neighbour and national context
  - Seasonal windows

**Classification:**
- `likely_error`: decimal signature or isolated move outside seasonal window
- `likely_real`: neighbours/national move same way, or inside seasonal window
- `unexplained`: otherwise

**Severity:**
- Critical: `likely_error` (cell quarantined)
- Warning: `unexplained`

**Incident scope:** `cell`

---

### 7. Reconciliation

**What it checks:**
- **Province vs cities:** province = mean of cities within Rp 50 rounding
- **National vs provinces:** ratio stays inside trailing robust band (0.9–1.1)

**Severity:**
- Critical: province vs cities mismatch
- Warning: national vs provinces ratio outside band

**Incident scope:** `province_day` or `commodity_date`

---

## Incident Store

All incidents are logged to `build/incidents/incident_events.db` (SQLite, append-only).

### Schema

```sql
CREATE TABLE incident_events (
    event_id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    at TEXT NOT NULL,
    check_name TEXT NOT NULL,
    severity TEXT NOT NULL,
    scope_type TEXT NOT NULL,
    scope_value TEXT NOT NULL,
    business_date TEXT NOT NULL,
    status TEXT NOT NULL,
    resolved_at TEXT,
    resolution TEXT,
    false_alarm INTEGER DEFAULT 0,
    run_id TEXT,
    issue_number INTEGER,
    evidence TEXT NOT NULL
);
```

### Statuses

- `open`: newly detected
- `resolved`: manually or auto-resolved
- `false_alarm_marked`: marked as false alarm
- `issue_linked`: linked to GitHub Issue

---

## GitHub Issues

Critical incidents that cannot be auto-resolved are opened as GitHub Issues.

### Labels

- `data-quality/critical`: critical severity
- `data-quality/freshness`, `data-quality/completeness`, etc.
- `needs-investigation`: still open

### Issue Template

```markdown
## Incident

- **Business date:** {business_date}
- **Check:** {check_name}
- **Severity:** critical
- **Incident ID:** {incident_id}

## Scope

{scope_value}

## Evidence

{evidence JSON}

## Resolution

Awaiting investigation.
```

---

## Running the Checks

```bash
# Run all checks for today
uv run hpdq check

# Run checks for a specific date
uv run hpdq check --date 2026-11-12

# Run checks with commodity filter
uv run hpdq check --commodity cabai-merah-besar
```

---

## Metrics

The incident store provides statistics:

```python
from hpdq.checks.incidents_store import IncidentStore

store = IncidentStore()
stats = store.get_statistics()

# Example output:
# {
#     "total_events": 156,
#     "by_check": {
#         "anomaly": 45,
#         "freshness": 30,
#         ...
#     },
#     "by_severity": {
#         "critical": 89,
#         "warning": 67
#     },
#     "open_incidents": 12,
#     "by_date": [...]
# }
```

---

## Next Steps (M4)

1. **Schedule**: Add cron to GitHub Actions (14:20 WIB + 17:20 WIB, Mon–Fri)
2. **Live incidents**: Connect to real data after M4
3. **Dashboard**: Show incident counts and trends on GitHub Pages
4. **Auto-resolution**: Implement auto-resolution for known patterns
