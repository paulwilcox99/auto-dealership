# External Hooks — Main Street Motors Simulation

This directory is reserved for external hook scripts that react to simulation events in real time.

## How it works

The simulation writes two coordination artifacts to `DB_DIR` after every worker execution:

1. **`simulation_state.json`** — high-level status per day (polling-friendly)
2. **`events.db`** — append-only SQLite event log (tail-friendly)

External programs should monitor these files rather than modifying the simulation's databases directly.

---

## simulation_state.json

Re-written after every worker completes. Example:

```json
{
  "status": "running",
  "current_date": "2025-03-14",
  "start_date": "2025-01-01",
  "end_date": "2025-04-01",
  "day_number": 72,
  "total_days": 90,
  "last_completed_worker": "sales_meeting",
  "last_updated": "2025-03-14T10:45:33Z",
  "workers_enabled": ["lead_creation", "walk_ins"],
  "workers_disabled": []
}
```

`status` values: `ready` | `running` | `paused` | `completed`

When `--step-mode` is active, `status` is set to `"paused"` before waiting for `[Enter]`, and back to `"running"` when advancing.  External programs can gate their actions on `status == "paused"` to run between days without race conditions.

---

## events.db — Event Log Schema

```sql
CREATE TABLE events (
    id              INTEGER PRIMARY KEY,
    sim_date        DATE    NOT NULL,
    sim_timestamp   DATETIME NOT NULL,
    worker_name     TEXT    NOT NULL,
    action          TEXT    NOT NULL,
    entity_type     TEXT,
    entity_id       INTEGER,
    old_status      TEXT,
    new_status      TEXT,
    amount          NUMERIC,
    description     TEXT
);
```

Open as a standard SQLite database and tail by `id` or `sim_timestamp`.

---

## Example hook patterns

### 1. React to every new lead (Python)

```python
import sqlite3, time, os

last_id = 0
db_path = os.path.join(os.getenv("DB_DIR", "./data"), "events.db")

while True:
    con = sqlite3.connect(db_path)
    rows = con.execute(
        "SELECT id, sim_date, description FROM events "
        "WHERE action='create' AND entity_type='lms_lead' AND id > ?",
        (last_id,)
    ).fetchall()
    con.close()
    for row in rows:
        last_id = row[0]
        print(f"NEW LEAD on {row[1]}: {row[2]}")
    time.sleep(1)
```

### 2. React to every vehicle sale (Python)

```python
import sqlite3, time, os

last_id = 0
db_path = os.path.join(os.getenv("DB_DIR", "./data"), "events.db")

while True:
    con = sqlite3.connect(db_path)
    rows = con.execute(
        "SELECT id, sim_date, amount, description FROM events "
        "WHERE action='sale' AND id > ?",
        (last_id,)
    ).fetchall()
    con.close()
    for row in rows:
        last_id = row[0]
        print(f"SALE on {row[1]}: ${row[2]:,.2f} — {row[3]}")
    time.sleep(1)
```

### 3. Wait for step-mode pause before acting (Python)

```python
import json, time, os

state_path = os.path.join(os.getenv("DB_DIR", "./data"), "simulation_state.json")

while True:
    try:
        with open(state_path) as f:
            state = json.load(f)
        if state.get("status") == "paused":
            print(f"Simulation paused on {state['current_date']} — running my hook...")
            # ... do work here ...
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    time.sleep(0.5)
```

---

## Disabling workers via .env

To hand off a worker to an external script entirely, set in `.env`:

```
DISABLE_WORKER_PAYDAY=true
DISABLE_WORKER_FINANCE_PAYMENTS=true
```

The simulation will skip those workers; your script becomes responsible for running the equivalent logic and updating the relevant databases directly.

---

## Database files

All files live in `DB_DIR` (default `./data`):

| File | Purpose |
|---|---|
| `sim_customers.db` | Customer pool |
| `sim_employees.db` | Employee pool |
| `cars_available.db` | Car pool |
| `sim_results.db` | Daily snapshots |
| `events.db` | Append-only event log |
| `lms.db` | Lead Management System |
| `crm.db` | Customer Relationship Manager |
| `dms.db` | Dealer Management System |
| `erp.db` | Transactions + employee payroll |
| `lss.db` | Loan Service System |
| `ems.db` | Scheduling + employee assignments |

All SQLite files use WAL journal mode for safe concurrent reads.
