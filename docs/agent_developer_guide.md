# Main Street Motors — Agent Developer Guide

This guide is for developers building AI agents that run alongside the dealership
simulation in a parallel process. It covers the full database schema, simulation
lifecycle, and the two patterns for keeping an agent in sync with the sim.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Database Reference](#database-reference)
   - [Simulation Databases](#simulation-databases)
   - [Company Databases](#company-databases)
3. [Simulation State File](#simulation-state-file)
4. [Event Log](#event-log)
5. [Worker Schedule](#worker-schedule)
6. [Day Lifecycle](#day-lifecycle)
7. [Synchronization Patterns](#synchronization-patterns)
   - [Free-Running Mode](#free-running-mode)
   - [Step-by-Step Mode](#step-by-step-mode)
8. [Reading from Databases Safely](#reading-from-databases-safely)
9. [Writing Back to Databases](#writing-back-to-databases)
10. [Configuration Reference](#configuration-reference)
11. [Status Enums Quick Reference](#status-enums-quick-reference)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│  main.py  (simulation process)                       │
│                                                      │
│  simulation/loop.py                                  │
│    └── workers run in order each day                 │
│        ├── reads/writes 11 SQLite DBs                │
│        └── writes simulation_state.json after        │
│            every worker                              │
└──────────────┬──────────────────────────────────────┘
               │  shared filesystem
┌──────────────▼──────────────────────────────────────┐
│  data/                                               │
│    ├── simulation_state.json  ← sync point           │
│    ├── events.db              ← append-only log      │
│    ├── lms.db   crm.db  dms.db                       │
│    ├── erp.db   lss.db  ems.db                       │
│    └── sim_customers.db  sim_employees.db            │
│        sim_cars.db  sim_results.db                   │
└──────────────┬──────────────────────────────────────┘
               │  shared filesystem
┌──────────────▼──────────────────────────────────────┐
│  Your agent process                                   │
│    ├── polls simulation_state.json                   │
│    ├── reads events.db for what happened             │
│    ├── queries company DBs for details               │
│    └── writes decisions back to company DBs          │
└─────────────────────────────────────────────────────┘
```

All 11 SQLite databases are opened in **WAL mode** (Write-Ahead Logging), which
allows your agent to read any database while the simulation is writing to it
without blocking or corrupting data.

The simulation's location for all files is `./data/` by default. Override with
the `DB_DIR` environment variable or the `--db-dir` CLI flag.

---

## Database Reference

All paths are relative to `DB_DIR` (default `./data/`).

### Simulation Databases

These track the virtual world the simulation draws from. Agents should treat them
as **read-only** unless they have a specific reason to alter the sim pool.

---

#### `sim_customers.db`

The pool of 1,000 synthetic customers. As the sim runs, customers move through
statuses as they interact with the dealership.

| Column    | Type          | Notes                                      |
|-----------|---------------|--------------------------------------------|
| id        | INTEGER PK    |                                            |
| name      | TEXT NOT NULL |                                            |
| address   | TEXT          |                                            |
| city      | TEXT          |                                            |
| state     | TEXT          |                                            |
| zip       | TEXT          |                                            |
| phone     | TEXT          |                                            |
| email     | TEXT          |                                            |
| status    | TEXT NOT NULL | `available` → `lead` or `walk-in` → `sold` |

**Status flow:**
```
available ──► lead (pulled by lead_creation)
available ──► walk-in (walk_ins worker)
lead / walk-in ──► sold (finance_sales closes)
```

---

#### `sim_employees.db`

The pool of 1,000 synthetic employees. The seeder assigns a subset to
departments and mirrors them into EMS and ERP.

| Column        | Type             | Notes                                      |
|---------------|------------------|--------------------------------------------|
| id            | INTEGER PK       |                                            |
| name          | TEXT NOT NULL    |                                            |
| address       | TEXT             |                                            |
| phone         | TEXT             |                                            |
| email         | TEXT             |                                            |
| weekly_salary | NUMERIC(10,2)    |                                            |
| department    | TEXT nullable    | `BD`, `sales`, `finance`, `accessories`, `service` |
| status        | TEXT NOT NULL    | `available`, `used`                        |

---

#### `sim_cars.db`

The pool of 1,000 synthetic vehicles. `min_price` is the dealer's cost — the
DMS records the same value and sells at a margin above it.

| Column    | Type             | Notes                                    |
|-----------|------------------|------------------------------------------|
| id        | INTEGER PK       |                                          |
| make      | TEXT NOT NULL    | e.g., `Toyota`                           |
| model     | TEXT NOT NULL    | e.g., `Camry`                            |
| year      | INTEGER NOT NULL |                                          |
| vin       | TEXT NOT NULL    | UNIQUE                                   |
| condition | TEXT NOT NULL    | `new` (2022–2025), `used` (2010–2022)   |
| min_price | NUMERIC(10,2)    | Dealer cost (new: $25k–$100k, used: $10k–$50k) |
| status    | TEXT NOT NULL    | `available`, `used`                      |

---

#### `sim_results.db`

One row per simulated day — the daily stats snapshot written by the reporter.
Useful for historical trend queries.

| Column          | Type          | Notes                        |
|-----------------|---------------|------------------------------|
| id              | INTEGER PK    |                              |
| sim_date        | DATE NOT NULL |                              |
| cars_sold       | INTEGER       |                              |
| cars_acquired   | INTEGER       |                              |
| new_leads       | INTEGER       |                              |
| leads_processed | INTEGER       |                              |
| cash_deals      | INTEGER       |                              |
| loans           | INTEGER       |                              |
| total_employees | INTEGER       |                              |
| total_revenue   | NUMERIC(12,2) |                              |
| total_car_costs | NUMERIC(12,2) |                              |
| total_salaries  | NUMERIC(12,2) |                              |

---

### Company Databases

These are the "real" business records. Your agents should primarily read and
write to these.

---

#### `lms.db` — Lead Management System

Tracks every prospect from first contact through to appointment scheduling.

| Column       | Type          | Notes                                           |
|--------------|---------------|-------------------------------------------------|
| id           | INTEGER PK    |                                                 |
| customer_name| TEXT NOT NULL |                                                 |
| address      | TEXT          |                                                 |
| phone        | TEXT          |                                                 |
| email        | TEXT          |                                                 |
| notes        | TEXT          | JSON array: `[{"date": "YYYY-MM-DD", "text": "…"}, …]` |
| status       | TEXT NOT NULL | See status flow below                           |
| last_updated | DATE          |                                                 |

**Status flow:**
```
new
 ├──► contacted  (lead_processing: 70% contact rate)
 │      ├──► interested     (50% of contacted)
 │      │      └──► scheduled  (schedule_lead: 40% of interested)
 │      ├──► not_interested  (30% of contacted)
 │      └──► (stays contacted)
 └──► (stays new — missed contact)
```
After a sale closes, `finance_sales` sets the lead status to `met`.

**Notes format** — read/write helpers on the ORM model:
```python
lead.get_notes()                      # → list of {date, text} dicts
lead.add_note("2025-03-01", "text")   # appends and re-serialises JSON
```

---

#### `crm.db` — Customer Relationship Management

Created when a customer arrives (walk-in or scheduled appointment). Tracks the
full sales interaction through to close or drop.

| Column          | Type          | Notes                                 |
|-----------------|---------------|---------------------------------------|
| id              | INTEGER PK    |                                       |
| customer_name   | TEXT NOT NULL |                                       |
| address         | TEXT          |                                       |
| phone           | TEXT          |                                       |
| email           | TEXT          |                                       |
| salesperson_name| TEXT          |                                       |
| meeting_date    | DATE          |                                       |
| notes           | TEXT          | JSON array same format as lms         |
| status          | TEXT NOT NULL | See status flow below                 |
| car_make        | TEXT          | Set when a car is shown               |
| car_model       | TEXT          |                                       |
| car_year        | INTEGER       |                                       |
| car_vin         | TEXT          |                                       |
| car_condition   | TEXT          |                                       |
| sale_price      | NUMERIC(10,2) | Set when deal closes                  |

**Status flow:**
```
scheduled
 ├──► no_show        (20% — sales_followup may reschedule)
 └──► met
       ├──► in_negotiation  (60% of met)
       │      ├──► sold      (finance_sales: ~60% close rate)
       │      └──► no_sale   (40% of in_negotiation)
       └──► waiting          (40% of met — no negotiation started)
```

---

#### `dms.db` — Dealer Management System

One row per vehicle on the lot. Created by `new_cars` worker, updated through
the sales process.

| Column           | Type          | Notes                                  |
|------------------|---------------|----------------------------------------|
| id               | INTEGER PK    |                                        |
| make             | TEXT NOT NULL |                                        |
| model            | TEXT NOT NULL |                                        |
| year             | INTEGER       |                                        |
| vin              | TEXT NOT NULL | UNIQUE                                 |
| condition        | TEXT NOT NULL | `new` or `used`                        |
| min_price        | NUMERIC(10,2) | Dealer cost (floor price)              |
| status           | TEXT NOT NULL | `available`, `in_negotiation`, `sold`  |
| sale_date        | DATE          | Set when sold                          |
| sale_price       | NUMERIC(10,2) | min_price × (1.0 – 1.15 margin)       |
| customer_name    | TEXT          | Set when sold                          |
| customer_address | TEXT          |                                        |
| customer_phone   | TEXT          |                                        |
| customer_email   | TEXT          |                                        |

---

#### `erp.db` — Enterprise Resource Planning

Two tables: employees (payroll records) and transactions (the general ledger).

**`erp_employees`**

| Column        | Type          | Notes                                 |
|---------------|---------------|---------------------------------------|
| id            | INTEGER PK    |                                       |
| name          | TEXT NOT NULL |                                       |
| weekly_salary | NUMERIC(10,2) |                                       |
| department    | TEXT          |                                       |

**`erp_transactions`** — append-only general ledger

| Column           | Type          | Notes                                  |
|------------------|---------------|----------------------------------------|
| id               | INTEGER PK    |                                        |
| transaction_type | TEXT NOT NULL | `credit` (income) or `debit` (expense) |
| amount           | NUMERIC(12,2) |                                        |
| payee_payer      | TEXT          | Customer name, employee name, etc.     |
| description      | TEXT          | Human-readable note                    |
| transaction_date | DATE NOT NULL |                                        |

**Credit sources:** vehicle sales (`finance_sales`), loan payments (`finance_payments`)
**Debit sources:** payroll (`payday`), inventory acquisition (`new_cars`)

---

#### `lss.db` — Loan Servicing System

One row per active or completed loan. `payments_left` counts down to zero.

| Column         | Type          | Notes                                     |
|----------------|---------------|-------------------------------------------|
| id             | INTEGER PK    |                                           |
| customer_name  | TEXT NOT NULL |                                           |
| address        | TEXT          |                                           |
| phone          | TEXT          |                                           |
| email          | TEXT          |                                           |
| start_date     | DATE          |                                           |
| payments_left  | INTEGER       | Counts down each month                    |
| payment_amount | NUMERIC(10,2) | Monthly payment                           |
| interest_rate  | NUMERIC(5,4)  | e.g., `0.0650` = 6.5%                    |
| down_payment   | NUMERIC(10,2) |                                           |
| original_price | NUMERIC(10,2) | Full vehicle sale price                   |

---

#### `ems.db` — Employee Management System

Tracks active employees and their scheduled appointments with customers.

**`ems_employees`**

| Column            | Type     | Notes                                   |
|-------------------|----------|-----------------------------------------|
| id                | INTEGER PK |                                       |
| name              | TEXT     |                                         |
| department        | TEXT     | `BD`, `sales`, `finance`, etc.          |
| current_customers | INTEGER  | Workload counter for round-robin assign  |
| last_assignment   | DATETIME |                                         |

**`ems_calendar`**

| Column         | Type     | Notes                                       |
|----------------|----------|---------------------------------------------|
| id             | INTEGER PK |                                           |
| employee_id    | INTEGER  | FK → ems_employees.id                       |
| customer_name  | TEXT     |                                             |
| scheduled_date | DATE     |                                             |
| scheduled_time | TIME     | Hour-aligned, from [9,10,11,13,14,15,16,17] |

---

## Simulation State File

**Path:** `{DB_DIR}/simulation_state.json`

The simulation rewrites this file after every worker and at every step-mode
pause. It is your primary synchronisation point.

```json
{
  "status": "running",
  "current_date": "2025-03-05",
  "start_date": "2025-02-18",
  "end_date": "2025-03-20",
  "day_number": 15,
  "total_days": 30,
  "last_completed_worker": "finance_sales",
  "last_updated": "2025-03-05T14:22:11.438210Z",
  "workers_enabled": [
    "lead_creation", "lead_processing", "schedule_lead",
    "walk_ins", "sales_meeting", "sales_followup",
    "new_cars", "finance_sales", "finance_payments", "payday"
  ],
  "workers_disabled": []
}
```

| Field                  | Type    | Notes                                                        |
|------------------------|---------|--------------------------------------------------------------|
| `status`               | string  | `running`, `paused` (step-mode), `completed`                |
| `current_date`         | string  | ISO 8601 date — the day currently being processed           |
| `start_date`           | string  | First day of the simulation                                  |
| `end_date`             | string  | Day the simulation will stop (exclusive — last day is end-1) |
| `day_number`           | int     | 1-indexed counter                                            |
| `total_days`           | int     | `(end_date - start_date).days`                              |
| `last_completed_worker`| string  | Name of last worker that ran, or `null`                     |
| `last_updated`         | string  | UTC ISO 8601 timestamp — use to detect stale state          |
| `workers_enabled`      | array   | Workers that are active this run                             |
| `workers_disabled`     | array   | Workers explicitly disabled via CLI or `.env`               |

**Reading this file safely:**

```python
import json, os

def read_state(db_dir="./data"):
    path = os.path.join(db_dir, "simulation_state.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)
```

The file is always written atomically by the sim (open → write → close). A read
that catches a partial write will raise `json.JSONDecodeError` — retry once if
that happens.

---

## Event Log

**Database:** `events.db`, table `events`

The event log is append-only and written by workers at significant moments. It
is the cleanest way for an agent to know *what happened* without polling every
company table.

| Column       | Type    | Populated by                                              |
|--------------|---------|-----------------------------------------------------------|
| id           | INTEGER | Auto                                                      |
| sim_date     | DATE    | Simulation date of the event                              |
| sim_timestamp| DATETIME| Wall-clock UTC time it was logged                         |
| worker_name  | TEXT    | e.g., `lead_creation`, `finance_sales`, `payday`          |
| action       | TEXT    | e.g., `create`, `sale`, `payroll`                         |
| entity_type  | TEXT    | e.g., `lms_lead`, `crm_record` — nullable                |
| entity_id    | INTEGER | PK of the affected record — nullable                      |
| old_status   | TEXT    | Status before change — nullable                           |
| new_status   | TEXT    | Status after change — nullable                            |
| amount       | NUMERIC | Financial value where relevant — nullable                 |
| description  | TEXT    | Human-readable summary                                    |

**Currently logged events:**

| Worker          | Action    | entity_type  | Notes                              |
|-----------------|-----------|--------------|------------------------------------|
| lead_creation   | create    | lms_lead     | New lead added                     |
| finance_sales   | sale      | crm_record   | Deal closed, amount = sale price   |
| payday          | payroll   | *(null)*     | Amount = total payroll             |

Not every worker logs to events — those that don't produce only console output.
Your agent can add its own event rows using the same table.

**Query new events since a known ID:**
```python
import sqlite3, os

def get_events_since(last_id, db_dir="./data"):
    conn = sqlite3.connect(os.path.join(db_dir, "events.db"))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM events WHERE id > ? ORDER BY id", (last_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
```

---

## Worker Schedule

Workers run in this fixed order every day. Whether a given worker actually
executes depends on the schedule below.

| # | Worker Name        | Schedule                                       | Key Output                        |
|---|--------------------|------------------------------------------------|-----------------------------------|
| 0 | `lead_creation`    | Every 5 days from start (`delta % 5 == 0`)    | New rows in `lms_leads`           |
| 1 | `lead_processing`  | Weekdays only (Mon–Fri)                        | LMS status advances               |
| 2 | `schedule_lead`    | Weekdays only                                  | LMS → `scheduled`, EMS calendar   |
| 3 | `walk_ins`         | Every day                                      | New CRM records, EMS assignments  |
| 4 | `sales_meeting`    | Every day                                      | CRM status advances, DMS locked   |
| 5 | `sales_followup`   | Every 3 days after start (`delta > 0 && delta % 3 == 0`) | CRM reschedules / drops |
| 6 | `new_cars`         | Every 5 days after start (`delta > 0 && delta % 5 == 0`) | DMS inventory added, ERP debit |
| 7 | `finance_sales`    | Every day                                      | CRM → `sold`, ERP credit, LSS loan|
| 8 | `finance_payments` | 1st of every month                             | LSS payments down, ERP credit     |
| 9 | `payday`           | Every Friday                                   | ERP debits, event logged          |

`delta` = `(current_date − start_date).days`

---

## Day Lifecycle

Understanding the exact sequence within a single day is essential for writing
correct agents.

```
Day N begins
│
├─ write_state("running", last_completed_worker=null)
│
├─ FOR each worker in schedule order:
│    ├─ [skip if not scheduled today]
│    ├─ worker.run(sim_date, rng)   ← DB reads/writes happen here
│    └─ write_state("running", last_completed_worker=<this worker>)
│
├─ reporter.record_day()           ← writes to sim_results.db
│
├─ [step-mode only]
│    ├─ write_state("paused", ...)
│    ├─ block on stdin
│    └─ write_state("running", ...)
│
└─ current_date += 1 day → Day N+1 begins
```

The state file is written **after each individual worker**, not once per day.
`last_completed_worker` tells you exactly how far through the day the sim has
progressed.

---

## Synchronization Patterns

### Free-Running Mode

In free-running mode the simulation runs as fast as it can. Your agent polls
`simulation_state.json` and reacts to day boundaries.

**Recommended pattern: watch for date changes**

```python
import json, time, os
from datetime import date

DB_DIR = "./data"
STATE_PATH = os.path.join(DB_DIR, "simulation_state.json")

def read_state():
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

def wait_for_next_day(known_date: str, poll_interval: float = 0.5) -> dict:
    """Block until simulation_state.json shows a new date. Returns new state."""
    while True:
        state = read_state()
        if state is None:
            time.sleep(poll_interval)
            continue
        if state["status"] == "completed":
            return state
        if state["current_date"] != known_date:
            return state
        time.sleep(poll_interval)

def run_agent():
    last_date = None

    while True:
        state = wait_for_next_day(last_date, poll_interval=0.25)

        if state["status"] == "completed":
            print("Simulation complete — agent shutting down")
            break

        sim_date = state["current_date"]
        day_number = state["day_number"]
        print(f"Agent: reacting to day {day_number} ({sim_date})")

        # --- your agent logic here ---
        # Read events that just occurred:
        #   new_events = get_events_since(last_event_id)
        # Read company DBs:
        #   leads = query_lms(sim_date)
        # Write decisions back:
        #   schedule_callback(lead_id, sim_date)
        # -----------------------------

        last_date = sim_date

if __name__ == "__main__":
    run_agent()
```

**Adding a minimum wait between days** (to throttle or simulate "real time"):

```python
import time

MIN_DAY_INTERVAL = 2.0  # seconds between agent reactions

def run_agent_throttled():
    last_date = None
    last_reaction_time = 0.0

    while True:
        state = wait_for_next_day(last_date, poll_interval=0.1)

        if state["status"] == "completed":
            break

        # Enforce minimum interval
        elapsed = time.monotonic() - last_reaction_time
        if elapsed < MIN_DAY_INTERVAL:
            time.sleep(MIN_DAY_INTERVAL - elapsed)

        sim_date = state["current_date"]
        # ... agent logic ...
        last_date = sim_date
        last_reaction_time = time.monotonic()
```

---

### Step-by-Step Mode

In step mode the simulation pauses after every day and waits for a newline on
`stdin` before advancing. This is the cleanest pattern for an agent that needs
guaranteed processing time before the sim moves on.

The sim writes `status: "paused"` to the state file, then blocks reading stdin.
Your agent detects the pause, does its work, then sends a newline to the sim's
stdin to release it.

**Pattern: launch the sim as a subprocess, control stdin**

```python
import subprocess, json, time, os, sys
from threading import Thread

DB_DIR = "./data"
STATE_PATH = os.path.join(DB_DIR, "simulation_state.json")

def read_state():
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

def wait_for_status(target_status: str, timeout: float = 30.0) -> dict | None:
    """Poll until state file shows the target status."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = read_state()
        if state and state["status"] == target_status:
            return state
        time.sleep(0.1)
    return None  # timed out

def run_agent_step_mode(days: int = 7, seed: int = 42):
    # Start the simulation in step mode, inheriting stdout/stderr so output
    # is visible, but taking control of stdin via a pipe.
    sim = subprocess.Popen(
        [
            ".venv/bin/python", "main.py",
            "--reset",
            f"--days={days}",
            f"--seed={seed}",
            "--step-mode",
        ],
        stdin=subprocess.PIPE,
        # stdout and stderr inherit from parent — you'll see sim output
    )

    try:
        while True:
            # Wait for the sim to pause at end of day
            state = wait_for_status("paused", timeout=60.0)

            if state is None:
                # Check if sim exited cleanly
                if sim.poll() is not None:
                    print("Simulation process ended")
                    break
                print("Warning: timed out waiting for paused state")
                break

            sim_date = state["current_date"]
            day_number = state["day_number"]
            print(f"\nAgent: sim paused after day {day_number} ({sim_date})")

            # --- your agent logic here ---
            # All workers for this day have completed at this point.
            # Read company DBs, make decisions, write back.
            do_agent_work(sim_date)
            # -----------------------------

            # Signal the sim to advance to the next day
            print(f"Agent: advancing sim to day {day_number + 1}")
            sim.stdin.write(b"\n")
            sim.stdin.flush()

            # Brief pause so sim can transition to "running" before we poll again
            time.sleep(0.2)

            # Check for completion
            final = read_state()
            if final and final["status"] == "completed":
                print("Simulation complete")
                break

    finally:
        sim.stdin.close()
        sim.wait()

def do_agent_work(sim_date: str):
    """Placeholder — implement your agent logic here."""
    import sqlite3
    conn = sqlite3.connect(os.path.join(DB_DIR, "lms.db"))
    new_leads = conn.execute(
        "SELECT id, customer_name FROM lms_leads WHERE status = 'new'"
    ).fetchall()
    conn.close()
    print(f"  Agent sees {len(new_leads)} uncontacted leads")
    # ... make decisions, write back, etc.

if __name__ == "__main__":
    run_agent_step_mode(days=7, seed=42)
```

**Step-mode timing guarantee:**

When your agent detects `status == "paused"`, all 10 workers for that day have
already completed. The databases reflect the full end-of-day state. You have
exclusive write access to the company databases (the sim is blocked on stdin
and will not touch them until you send the newline).

---

## Reading from Databases Safely

All databases use WAL mode. You can open a read connection at any time without
blocking or corrupting the sim's writes.

**Using raw sqlite3 (no dependencies):**

```python
import sqlite3, os

def query(db_name: str, sql: str, params=(), db_dir="./data"):
    path = os.path.join(db_dir, db_name)
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)  # read-only
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# Examples
leads = query("lms.db", "SELECT * FROM lms_leads WHERE status = 'new'")

negotiations = query(
    "crm.db",
    "SELECT * FROM crm_records WHERE status = 'in_negotiation'"
)

inventory = query(
    "dms.db",
    "SELECT make, model, year, min_price FROM dms_cars WHERE status = 'available'"
)

recent_sales = query(
    "erp.db",
    "SELECT * FROM erp_transactions WHERE transaction_type = 'credit' ORDER BY id DESC LIMIT 20"
)
```

**Using SQLAlchemy (same engine the sim uses):**

```python
import sys
sys.path.insert(0, "/home/paul/code/auto_dealership")

from database.session import session_for
from models.company_models import LMSLead, CRMRecord, DMSCar

session = session_for("lms.db")
leads = session.query(LMSLead).filter_by(status="new").all()
session.close()
```

---

## Writing Back to Databases

Your agent can write to any company database. The simulation uses the same
SQLAlchemy session pattern — follow the same conventions to avoid conflicts.

**Safe columns to write to:**

| Database | Safe writes                                                    |
|----------|----------------------------------------------------------------|
| `lms.db` | `notes`, `status`, `last_updated` on existing leads           |
| `crm.db` | `notes`, `status` on existing records                         |
| `dms.db` | `status` on cars (e.g., mark reserved)                        |
| `erp.db` | New `erp_transactions` rows                                    |
| `ems.db` | New `ems_calendar` rows                                        |
| `events.db` | New event rows to log agent actions                         |

**Example — add a note to a lead:**

```python
import sqlite3, json, os
from datetime import date

def add_lead_note(lead_id: int, note_text: str, sim_date: date, db_dir="./data"):
    path = os.path.join(db_dir, "lms.db")
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")

    row = conn.execute(
        "SELECT notes FROM lms_leads WHERE id = ?", (lead_id,)
    ).fetchone()
    if row is None:
        conn.close()
        return

    notes = json.loads(row[0] or "[]")
    notes.append({"date": sim_date.isoformat(), "text": note_text})

    conn.execute(
        "UPDATE lms_leads SET notes = ?, last_updated = ? WHERE id = ?",
        (json.dumps(notes), sim_date.isoformat(), lead_id)
    )
    conn.commit()
    conn.close()
```

**Example — log an agent action to events.db:**

```python
from datetime import datetime, date

def log_agent_event(sim_date: date, action: str, description: str, db_dir="./data"):
    conn = sqlite3.connect(os.path.join(db_dir, "events.db"))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """INSERT INTO events
           (sim_date, sim_timestamp, worker_name, action, description)
           VALUES (?, ?, ?, ?, ?)""",
        (
            sim_date.isoformat(),
            datetime.utcnow().isoformat() + "Z",
            "agent",          # use a distinctive name for your agent
            action,
            description,
        )
    )
    conn.commit()
    conn.close()
```

**Avoid:**
- Writing to `sim_customers`, `sim_employees`, `sim_cars` — these are the sim's
  internal pool and changes here affect seeding logic
- Writing to `sim_results` — owned by the reporter
- Deleting rows from any table — the sim expects records to exist once created
- Changing `status` fields without understanding the full flow (e.g., a car
  marked `sold` in DMS should also have a CRM record in `sold` status)

---

## Configuration Reference

**Environment variables** (`.env` file or shell):

| Variable                    | Default    | Notes                                           |
|-----------------------------|------------|-------------------------------------------------|
| `DB_DIR`                    | `./data`   | Directory for all DBs and state.json            |
| `DB_DRIVER`                 | `sqlite`   | Only sqlite supported currently                 |
| `OPENAI_API_KEY`            | *(empty)*  | If empty, notes use template fallbacks          |
| `DISABLE_WORKER_<NAME>=true`| *(unset)*  | e.g., `DISABLE_WORKER_PAYDAY=true`              |

**Key simulation constants** (from `config.py`):

| Constant                 | Value       | Meaning                                      |
|--------------------------|-------------|----------------------------------------------|
| `LEAD_CREATION_INTERVAL` | 5 days      | New leads every 5 days                       |
| `NEW_CARS_INTERVAL`      | 5 days      | Inventory restocked every 5 days             |
| `SALES_FOLLOWUP_INTERVAL`| 3 days      | Follow-up sweep every 3 days                 |
| `WALK_IN_MIN/MAX`        | 1–5         | Walk-ins per day                             |
| `LEAD_CREATION_BATCH_MIN/MAX` | 10–30  | Leads created per creation run              |
| `NEW_CARS_BATCH_MIN/MAX` | 5–15        | Cars added to inventory per restock run      |
| `FINANCE_LOAN_RATE`      | 0.65        | 65% of sales are financed                   |
| `SALES_NO_SHOW_RATE`     | 0.20        | 20% of appointments are no-shows            |
| `LEAD_CONTACT_RATE`      | 0.70        | 70% of new leads are successfully reached   |
| `LLM_MAX_CALLS_PER_WORKER` | 10        | Max OpenAI calls per worker per day         |

---

## Status Enums Quick Reference

```
sim_customers.status:   available → lead | walk-in → sold
sim_employees.status:   available | used
sim_cars.status:        available | used

lms_leads.status:       new → contacted → interested → scheduled
                                        → not_interested
                        (any) → met (after sale)

crm_records.status:     scheduled → no_show
                                  → met → waiting
                                       → in_negotiation → sold
                                                        → no_sale
                                       → no_sale

dms_cars.status:        available → in_negotiation → sold
                                  → available (if no_sale)

erp_transactions.type:  credit (income) | debit (expense)
```

---

## Common Agent Recipes

### "What happened today?"

```python
def summarise_day(sim_date: str, db_dir="./data"):
    events = query("events.db",
        "SELECT * FROM events WHERE sim_date = ? ORDER BY id",
        (sim_date,), db_dir)

    sales = query("crm.db",
        "SELECT customer_name, sale_price, car_make, car_model, car_year "
        "FROM crm_records WHERE status = 'sold' AND meeting_date = ?",
        (sim_date,), db_dir)

    new_leads = query("lms.db",
        "SELECT COUNT(*) as n FROM lms_leads WHERE last_updated = ? AND status = 'new'",
        (sim_date,), db_dir)

    return {"events": events, "sales": sales, "new_leads": new_leads[0]["n"]}
```

### "Which customers need follow-up?"

```python
def leads_needing_attention(db_dir="./data"):
    return query("lms.db",
        """SELECT id, customer_name, status, last_updated
           FROM lms_leads
           WHERE status IN ('new', 'contacted', 'interested', 'schedule')
           ORDER BY last_updated ASC""",
        db_dir=db_dir)
```

### "What's the current inventory value?"

```python
def inventory_value(db_dir="./data"):
    rows = query("dms.db",
        "SELECT SUM(min_price) as cost, COUNT(*) as count "
        "FROM dms_cars WHERE status = 'available'",
        db_dir=db_dir)
    return rows[0]
```

### "What is the P&L so far?"

```python
def pnl(db_dir="./data"):
    rows = query("erp.db",
        """SELECT transaction_type, SUM(amount) as total
           FROM erp_transactions GROUP BY transaction_type""",
        db_dir=db_dir)
    totals = {r["transaction_type"]: float(r["total"]) for r in rows}
    return {
        "revenue": totals.get("credit", 0),
        "expenses": totals.get("debit", 0),
        "net": totals.get("credit", 0) - totals.get("debit", 0),
    }
```
