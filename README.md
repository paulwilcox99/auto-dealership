# Main Street Motors — Dealership Simulation

A day-by-day Python simulation of a car dealership's business operations. Workers run each day to move customers through the BD → Sales → Finance pipeline, writing to a set of SQLite databases that external programs can monitor in real time.

## Features

- **10 scheduled workers** — lead creation, processing, scheduling, walk-ins, sales meetings, follow-ups, inventory restocking, finance/loans, payment collection, and payroll
- **11 SQLite databases** in WAL mode for safe concurrent reads by external programs
- **Abstract repository layer** — swap SQLite for PostgreSQL or MongoDB by changing one line in `.env`
- **LLM note generation** — uses `gpt-4o-mini` to write realistic CRM/LMS notes; falls back to 33 built-in templates when offline or rate-limited
- **`simulation_state.json`** — written after every worker so external scripts can coordinate
- **Append-only `events.db`** — every state transition is logged for external programs to tail
- **Step mode** — pause after each day with `[Enter]` to advance, ideal for watching external integrations react in real time
- **Reproducible runs** — pass `--seed` for deterministic output
- **Rich terminal output** — colored per-worker logs, summary tables, and an end-of-simulation report

## Quickstart

```bash
# 1. Clone and set up
git clone https://github.com/paulwilcox99/auto-dealership
cd auto-dealership
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure (optional — simulation runs without an OpenAI key)
cp .env.example .env
# edit .env to add OPENAI_API_KEY

# 3. Run
python main.py --reset --days 30 --seed 42
```

## CLI Reference

```
python main.py [options]

  --days N               Number of simulation days (default: 30)
  --start-date YYYY-MM-DD  Start date (default: today)
  --reset                Drop and re-initialize all databases before running
  --seed N               Random seed for reproducible runs
  --step-mode            Pause after each day and wait for [Enter]
  --disable-workers W    Comma-separated worker names to skip
  --disable-all-workers  Skip all workers (hand off to external scripts)
  --db-dir PATH          Override the database directory
```

**Examples**

```bash
# Reproducible 90-day run starting from a specific date
python main.py --start-date 2025-01-01 --days 90 --seed 42

# Step through days manually, watching DBs update in real time
python main.py --days 30 --step-mode

# Let an external script own the payday and finance_payments workers
python main.py --days 30 --disable-workers payday,finance_payments

# Fully external — simulation manages state only
python main.py --days 30 --disable-all-workers
```

## Project Structure

```
auto_dealership/
├── main.py                     # CLI entry point
├── config.py                   # All constants and probability weights
├── data/
│   ├── cars_data.py            # 18 makes × 3–6 models lookup table
│   └── note_templates.py       # 33 fallback note templates
├── models/
│   ├── sim_models.py           # ORM models: customers, employees, cars, results, events
│   └── company_models.py       # ORM models: LMS, CRM, DMS, ERP, LSS, EMS
├── database/
│   ├── base.py                 # Abstract BaseRepository interface
│   ├── session.py              # WAL-mode SQLite engine factory
│   └── repositories/           # One file per database table
├── initialization/
│   └── seeder.py               # Faker-based DB population (1,000 customers/employees/cars)
├── simulation/
│   ├── loop.py                 # Day loop and worker scheduling
│   ├── state.py                # simulation_state.json read/write
│   ├── events.py               # Append to events.db
│   └── llm.py                  # OpenAI notes + cache + fallback
├── workers/
│   ├── lead_creation.py        # Day 0, then every 5 days
│   ├── lead_processing.py      # Weekdays
│   ├── schedule_lead.py        # Weekdays
│   ├── walk_ins.py             # Every day
│   ├── sales_meeting.py        # Every day
│   ├── sales_followup.py       # Every 3 days
│   ├── new_cars.py             # Every 5 days
│   ├── finance_sales.py        # Every day
│   ├── finance_payments.py     # 1st of each month
│   └── payday.py               # Every Friday
├── reporting/
│   └── reporter.py             # Daily DB snapshot + end-of-simulation report
└── hooks/
    └── README.md               # Guide for external hook scripts
```

## Databases

All files live in `./data/` (configurable via `DB_DIR` in `.env`):

| File | Type | Purpose |
|---|---|---|
| `sim_customers.db` | Simulation | 1,000 generated customers |
| `sim_employees.db` | Simulation | 1,000 generated employees |
| `cars_available.db` | Simulation | 1,000 generated vehicles |
| `sim_results.db` | Simulation | One row per simulated day |
| `events.db` | Simulation | Append-only event log |
| `lms.db` | Company | Lead Management System |
| `crm.db` | Company | Customer Relationship Manager |
| `dms.db` | Company | Dealer Management System |
| `erp.db` | Company | Transactions + payroll |
| `lss.db` | Company | Loan Service System |
| `ems.db` | Company | Employee scheduling |

All SQLite databases use WAL journal mode so external programs can read while the simulation is writing.

## External Integration

After every worker completes, the simulation writes `simulation_state.json`:

```json
{
  "status": "running",
  "current_date": "2025-03-14",
  "day_number": 72,
  "total_days": 90,
  "last_completed_worker": "sales_meeting",
  "workers_enabled": ["lead_creation", "walk_ins", "..."],
  "workers_disabled": []
}
```

`status` is `"paused"` between days in `--step-mode`, giving external scripts a clean window to act. See [`hooks/README.md`](hooks/README.md) for example polling scripts.

## Swapping the Database Backend

Change `DB_DRIVER` in `.env` and add a branch in `database/session.py`. Workers call only repository methods — no DB-specific code leaks outside the `database/` layer.

```
DB_DRIVER=postgresql   # future support
```

## Disabling Workers via Environment

Any worker can be handed off to an external script by setting a flag in `.env`:

```
DISABLE_WORKER_PAYDAY=true
DISABLE_WORKER_FINANCE_PAYMENTS=true
```
