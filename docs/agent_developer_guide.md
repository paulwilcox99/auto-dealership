# Main Street Motors — Agent Developer Guide

This guide is for developers building AI agents that interact with the Main Street Motors
dealership databases. Agents connect to the business databases directly, poll a single
JSON file to know when a new business day has started, and then read and write the
databases as they would in a live dealership environment.

**Agents do not need to know anything about the simulation.** From your agent's
perspective, the databases are live dealership systems. The only simulation artifact
your agent touches is `simulation_state.json`, which serves as a lightweight clock
signal telling the agent that a new day's data is ready.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Database Reference](#database-reference)
   - [`cars_available.db`](#cars_availabledb)
   - [`lms.db`](#lmsdb--lead-management-system)
   - [`crm.db`](#crmdb--customer-relationship-management)
   - [`dms.db`](#dmsdb--dealer-management-system)
   - [`erp.db`](#erpdb--enterprise-resource-planning)
   - [`lss.db`](#lssdb--loan-servicing-system)
   - [`ems.db`](#emsdb--employee-management-system)
3. [How Agents Are Triggered](#how-agents-are-triggered)
4. [Polling Pattern](#polling-pattern)
5. [Reading from Databases](#reading-from-databases)
6. [Writing Back to Databases](#writing-back-to-databases)
7. [Status Enums Quick Reference](#status-enums-quick-reference)
8. [Common Agent Recipes](#common-agent-recipes)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│  data/  (shared directory)                           │
│                                                      │
│  ── Clock signal ──────────────────────────────────  │
│    simulation_state.json   ← agent polls this        │
│                                                      │
│  ── Business databases (agent reads & writes) ─────  │
│    cars_available.db                                 │
│    lms.db    crm.db    dms.db                        │
│    erp.db    lss.db    ems.db                        │
│                                                      │
│  ── Off-limits to agents ──────────────────────────  │
│    sim_customers.db   sim_employees.db               │
│    sim_results.db     events.db                      │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│  Your agent process                                   │
│    1. Poll simulation_state.json every few seconds   │
│    2. When current_date changes → run agent logic    │
│    3. Query the 7 business databases                 │
│    4. Write decisions back to those databases        │
└─────────────────────────────────────────────────────┘
```

All databases use **WAL mode** (Write-Ahead Logging), so your agent can read at any
time without blocking writes or corrupting data.

All files live in `./data/` by default. Override with the `DB_DIR` environment variable.

---

## Database Reference

Your agent should read from and write to these seven databases only.

---

### `cars_available.db`

The dealership's vehicle catalogue — every car that has ever been available for sale.
Use this to look up vehicle details by VIN or to find what stock exists.

**Table: `sim_cars`**

| Column    | Type             | Notes                                         |
|-----------|------------------|-----------------------------------------------|
| id        | INTEGER PK       |                                               |
| make      | TEXT NOT NULL    | e.g., `Toyota`                                |
| model     | TEXT NOT NULL    | e.g., `Camry`                                 |
| year      | INTEGER NOT NULL |                                               |
| vin       | TEXT NOT NULL    | UNIQUE                                        |
| condition | TEXT NOT NULL    | `new` (2022–2025) or `used` (2010–2022)       |
| min_price | NUMERIC(10,2)    | Dealer cost (new: $25k–$100k, used: $10k–$50k) |
| status    | TEXT NOT NULL    | `available` (in catalogue), `used` (on lot)   |

---

### `lms.db` — Lead Management System

Tracks every prospect from first contact through to appointment scheduling.

**Table: `lms_leads`**

| Column        | Type          | Notes                                                      |
|---------------|---------------|------------------------------------------------------------|
| id            | INTEGER PK    |                                                            |
| customer_name | TEXT NOT NULL |                                                            |
| address       | TEXT          |                                                            |
| phone         | TEXT          |                                                            |
| email         | TEXT          |                                                            |
| notes         | TEXT          | JSON array: `[{"date": "YYYY-MM-DD", "text": "…"}, …]`    |
| status        | TEXT NOT NULL | See status flow below                                      |
| last_updated  | DATE          |                                                            |

**Status flow:**
```
new
 ├──► contacted
 │      ├──► interested
 │      │      └──► scheduled
 │      └──► not_interested
 └──► (stays new — contact missed)

(any status) ──► met   (after a sale closes)
```

**Notes format:**
```python
# Notes are stored as a JSON array. Read and append like this:
import json

row = conn.execute("SELECT notes FROM lms_leads WHERE id = ?", (lead_id,)).fetchone()
notes = json.loads(row["notes"] or "[]")
notes.append({"date": "2025-03-01", "text": "Called, very interested in SUVs."})
conn.execute("UPDATE lms_leads SET notes = ?, last_updated = ? WHERE id = ?",
             (json.dumps(notes), "2025-03-01", lead_id))
conn.commit()
```

---

### `crm.db` — Customer Relationship Management

Created when a customer arrives (walk-in or scheduled appointment). Tracks the full
sales interaction from arrival through to close or drop.

**Table: `crm_records`**

| Column           | Type          | Notes                                  |
|------------------|---------------|----------------------------------------|
| id               | INTEGER PK    |                                        |
| customer_name    | TEXT NOT NULL |                                        |
| address          | TEXT          |                                        |
| phone            | TEXT          |                                        |
| email            | TEXT          |                                        |
| salesperson_name | TEXT          |                                        |
| meeting_date     | DATE          |                                        |
| notes            | TEXT          | JSON array, same format as `lms_leads` |
| status           | TEXT NOT NULL | See status flow below                  |
| car_make         | TEXT          | Set when a car is shown                |
| car_model        | TEXT          |                                        |
| car_year         | INTEGER       |                                        |
| car_vin          | TEXT          |                                        |
| car_condition    | TEXT          |                                        |
| sale_price       | NUMERIC(10,2) | Set when deal closes                   |

**Status flow:**
```
scheduled
 ├──► no_show
 └──► met
       ├──► in_negotiation
       │      ├──► sold
       │      └──► no_sale
       └──► waiting
```

---

### `dms.db` — Dealer Management System

One row per vehicle on the lot. This is the live inventory record — what is on the
floor, what is being negotiated, and what has sold.

**Table: `dms_cars`**

| Column           | Type          | Notes                                   |
|------------------|---------------|-----------------------------------------|
| id               | INTEGER PK    |                                         |
| make             | TEXT NOT NULL |                                         |
| model            | TEXT NOT NULL |                                         |
| year             | INTEGER       |                                         |
| vin              | TEXT NOT NULL | UNIQUE                                  |
| condition        | TEXT NOT NULL | `new` or `used`                         |
| min_price        | NUMERIC(10,2) | Dealer cost (floor price)               |
| status           | TEXT NOT NULL | `available`, `in_negotiation`, `sold`   |
| sale_date        | DATE          | Set when sold                           |
| sale_price       | NUMERIC(10,2) | Typically min_price × 1.0–1.15 margin   |
| customer_name    | TEXT          | Set when sold                           |
| customer_address | TEXT          |                                         |
| customer_phone   | TEXT          |                                         |
| customer_email   | TEXT          |                                         |

**Status flow:**
```
available ──► in_negotiation ──► sold
                             └──► available  (if deal falls through)
```

---

### `erp.db` — Enterprise Resource Planning

Two tables: employee payroll records and the general ledger.

**Table: `erp_employees`**

| Column        | Type          | Notes                              |
|---------------|---------------|------------------------------------|
| id            | INTEGER PK    |                                    |
| name          | TEXT NOT NULL |                                    |
| weekly_salary | NUMERIC(10,2) |                                    |
| department    | TEXT          | `BD`, `sales`, `finance`, etc.     |

**Table: `erp_transactions`** — append-only general ledger

| Column           | Type          | Notes                                   |
|------------------|---------------|-----------------------------------------|
| id               | INTEGER PK    |                                         |
| transaction_type | TEXT NOT NULL | `credit` (income) or `debit` (expense)  |
| amount           | NUMERIC(12,2) |                                         |
| payee_payer      | TEXT          | Customer name, employee name, etc.      |
| description      | TEXT          | Human-readable note                     |
| transaction_date | DATE NOT NULL |                                         |

**Credits:** vehicle sales, loan payments received
**Debits:** payroll, inventory purchases

---

### `lss.db` — Loan Servicing System

One row per loan. `payments_left` counts down to zero as monthly payments are received.

**Table: `lss_loans`**

| Column         | Type          | Notes                              |
|----------------|---------------|------------------------------------|
| id             | INTEGER PK    |                                    |
| customer_name  | TEXT NOT NULL |                                    |
| address        | TEXT          |                                    |
| phone          | TEXT          |                                    |
| email          | TEXT          |                                    |
| start_date     | DATE          |                                    |
| payments_left  | INTEGER       | Counts down each month             |
| payment_amount | NUMERIC(10,2) | Monthly payment                    |
| interest_rate  | NUMERIC(5,4)  | e.g., `0.0650` = 6.5%             |
| down_payment   | NUMERIC(10,2) |                                    |
| original_price | NUMERIC(10,2) | Full vehicle sale price            |

---

### `ems.db` — Employee Management System

Tracks active employees and their appointment calendars.

**Table: `ems_employees`**

| Column            | Type          | Notes                                    |
|-------------------|---------------|------------------------------------------|
| id                | INTEGER PK    |                                          |
| name              | TEXT          |                                          |
| department        | TEXT          | `BD`, `sales`, `finance`, etc.           |
| current_customers | INTEGER       | Workload counter for round-robin assigns |
| last_assignment   | DATETIME      |                                          |

**Table: `ems_calendar`**

| Column         | Type          | Notes                                         |
|----------------|---------------|-----------------------------------------------|
| id             | INTEGER PK    |                                               |
| employee_id    | INTEGER       | FK → ems_employees.id                         |
| customer_name  | TEXT          |                                               |
| scheduled_date | DATE          |                                               |
| scheduled_time | TIME          | Hour-aligned: 9, 10, 11, 13, 14, 15, 16, 17  |

---

## How Agents Are Triggered

Your agent does not need to know how or when the underlying data changes. Instead,
poll `simulation_state.json` every few seconds. When the `current_date` field
changes, a full business day has completed and the databases reflect the new state.
Run your agent logic, then go back to polling.

**`simulation_state.json` — the fields your agent cares about:**

```json
{
  "status": "running",
  "current_date": "2025-03-05",
  "end_date": "2025-03-20"
}
```

| Field          | Type   | Notes                                                          |
|----------------|--------|----------------------------------------------------------------|
| `status`       | string | `running` or `completed` — stop your agent when `completed`   |
| `current_date` | string | ISO 8601 date. When this changes, a new day's data is ready.  |
| `end_date`     | string | The date the run ends (exclusive). Informational only.         |

That is all your agent needs to read from this file. Ignore all other fields.

---

## Polling Pattern

Poll `simulation_state.json` every 2–5 seconds. When `current_date` changes from
the last value your agent saw, the day is complete and it is safe to read and write
the business databases.

```python
import json
import os
import sqlite3
import time

DB_DIR = "./data"
STATE_PATH = os.path.join(DB_DIR, "simulation_state.json")


def read_state() -> dict | None:
    """Read simulation_state.json. Returns None on missing file or bad JSON."""
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def run_agent(poll_interval: float = 3.0) -> None:
    """
    Main agent loop. Polls for a date change every `poll_interval` seconds,
    then runs agent logic once per day.
    """
    last_date = None

    while True:
        state = read_state()

        if state is None:
            # State file not written yet — wait and retry
            time.sleep(poll_interval)
            continue

        if state["status"] == "completed":
            print("Run complete — agent shutting down.")
            break

        current_date = state["current_date"]

        if current_date != last_date:
            print(f"New day detected: {current_date}")
            do_agent_work(current_date)
            last_date = current_date

        time.sleep(poll_interval)


def do_agent_work(current_date: str) -> None:
    """
    Called once per day when current_date changes.
    Read the business databases, make decisions, write back.
    """
    # Example: count open leads
    conn = sqlite3.connect(os.path.join(DB_DIR, "lms.db"))
    conn.row_factory = sqlite3.Row
    open_leads = conn.execute(
        "SELECT COUNT(*) as n FROM lms_leads WHERE status IN ('new', 'contacted', 'interested')"
    ).fetchone()["n"]
    conn.close()

    print(f"  {current_date}: {open_leads} leads need attention")
    # ... query other databases, write decisions back ...


if __name__ == "__main__":
    run_agent(poll_interval=3.0)
```

---

## Reading from Databases

All databases use WAL mode. You can open a connection at any time — it will never
block or conflict with other writes happening in the background.

```python
import sqlite3
import os

DB_DIR = "./data"


def query(db_name: str, sql: str, params: tuple = ()) -> list[dict]:
    """Query any business database."""
    path = os.path.join(DB_DIR, db_name)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# Examples

# All uncontacted leads
leads = query("lms.db", "SELECT * FROM lms_leads WHERE status = 'new'")

# Deals currently in negotiation
negotiations = query(
    "crm.db",
    "SELECT * FROM crm_records WHERE status = 'in_negotiation'"
)

# Available inventory on the lot
inventory = query(
    "dms.db",
    "SELECT make, model, year, condition, min_price FROM dms_cars WHERE status = 'available'"
)

# Recent sales revenue
recent_sales = query(
    "erp.db",
    "SELECT * FROM erp_transactions WHERE transaction_type = 'credit' ORDER BY id DESC LIMIT 20"
)

# Active loans
active_loans = query(
    "lss.db",
    "SELECT * FROM lss_loans WHERE payments_left > 0"
)
```

---

## Writing Back to Databases

Write to the business databases using standard SQLite connections. Always open with
`PRAGMA journal_mode=WAL` to stay consistent with how the databases were created.

**What you can write:**

| Database             | Writable columns / operations                               |
|----------------------|-------------------------------------------------------------|
| `cars_available.db`  | `status` on existing cars                                   |
| `lms.db`             | `notes`, `status`, `last_updated` on existing leads        |
| `crm.db`             | `notes`, `status`, `sale_price` on existing records        |
| `dms.db`             | `status`, `sale_date`, `sale_price`, customer fields        |
| `erp.db`             | New rows in `erp_transactions`; update `erp_balance`        |
| `lss.db`             | New loan rows; update `payments_left`                       |
| `ems.db`             | New rows in `ems_calendar`; update `ems_employees`          |

**Do not:**
- Delete rows from any table — records are expected to persist once created
- Change `status` fields in a way that skips steps in the flow (e.g., jumping a
  CRM record from `scheduled` directly to `sold` without an intermediate state)

**Example — add a note to a lead:**

```python
import sqlite3
import json
import os

DB_DIR = "./data"


def add_lead_note(lead_id: int, note_text: str, note_date: str) -> None:
    path = os.path.join(DB_DIR, "lms.db")
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")

    row = conn.execute(
        "SELECT notes FROM lms_leads WHERE id = ?", (lead_id,)
    ).fetchone()
    if row is None:
        conn.close()
        return

    notes = json.loads(row[0] or "[]")
    notes.append({"date": note_date, "text": note_text})

    conn.execute(
        "UPDATE lms_leads SET notes = ?, last_updated = ? WHERE id = ?",
        (json.dumps(notes), note_date, lead_id)
    )
    conn.commit()
    conn.close()
```

**Example — schedule a follow-up appointment:**

```python
def schedule_appointment(employee_id: int, customer_name: str,
                         appt_date: str, appt_hour: int) -> None:
    """Add an entry to the EMS calendar."""
    path = os.path.join(DB_DIR, "ems.db")
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """INSERT INTO ems_calendar (employee_id, customer_name, scheduled_date, scheduled_time)
           VALUES (?, ?, ?, ?)""",
        (employee_id, customer_name, appt_date, f"{appt_hour:02d}:00:00")
    )
    conn.commit()
    conn.close()
```

**Example — record a custom transaction in the ledger:**

```python
def record_transaction(transaction_type: str, amount: float,
                       payee_payer: str, description: str, txn_date: str) -> None:
    path = os.path.join(DB_DIR, "erp.db")
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """INSERT INTO erp_transactions
           (transaction_type, amount, payee_payer, description, transaction_date)
           VALUES (?, ?, ?, ?, ?)""",
        (transaction_type, amount, payee_payer, description, txn_date)
    )
    conn.commit()
    conn.close()
```

---

## Status Enums Quick Reference

```
lms_leads.status:
    new → contacted → interested → scheduled
                    → not_interested
    (any) → met  (after sale closes)

crm_records.status:
    scheduled → no_show
              → met → in_negotiation → sold
                    │               → no_sale
                    └──► waiting

dms_cars.status:
    available → in_negotiation → sold
                               → available  (deal fell through)

erp_transactions.transaction_type:
    credit  (income: sales, loan payments)
    debit   (expense: payroll, inventory purchases)
```

---

## Common Agent Recipes

### "Which leads need attention today?"

```python
def leads_needing_attention() -> list[dict]:
    return query("lms.db",
        """SELECT id, customer_name, status, last_updated
           FROM lms_leads
           WHERE status IN ('new', 'contacted', 'interested')
           ORDER BY last_updated ASC""")
```

### "What sales closed today?"

```python
def sales_closed_on(date: str) -> list[dict]:
    return query("crm.db",
        """SELECT customer_name, salesperson_name, car_make, car_model,
                  car_year, sale_price
           FROM crm_records
           WHERE status = 'sold' AND meeting_date = ?""",
        (date,))
```

### "What is the current inventory?"

```python
def available_inventory() -> list[dict]:
    return query("dms.db",
        """SELECT make, model, year, condition, min_price
           FROM dms_cars
           WHERE status = 'available'
           ORDER BY make, model""")
```

### "What is the P&L so far?"

```python
def pnl() -> dict:
    rows = query("erp.db",
        """SELECT transaction_type, SUM(amount) as total
           FROM erp_transactions
           GROUP BY transaction_type""")
    totals = {r["transaction_type"]: float(r["total"]) for r in rows}
    return {
        "revenue":  totals.get("credit", 0.0),
        "expenses": totals.get("debit",  0.0),
        "net":      totals.get("credit", 0.0) - totals.get("debit", 0.0),
    }
```

### "What is the active loan portfolio value?"

```python
def loan_portfolio_value() -> float:
    rows = query("lss.db",
        "SELECT payments_left, payment_amount FROM lss_loans WHERE payments_left > 0")
    return sum(float(r["payments_left"]) * float(r["payment_amount"]) for r in rows)
```

### "Which appointments are scheduled for a given date?"

```python
def appointments_on(date: str) -> list[dict]:
    return query("ems.db",
        """SELECT e.name as employee, e.department,
                  c.customer_name, c.scheduled_time
           FROM ems_calendar c
           JOIN ems_employees e ON e.id = c.employee_id
           WHERE c.scheduled_date = ?
           ORDER BY c.scheduled_time""",
        (date,))
```
