"""
sample_agent.py — Main Street Motors BD Manager Agent

Monitors simulation_state.json every few seconds. When current_date changes,
a new business day has completed and the agent runs its daily logic against
the dealership databases.

The agent has no knowledge of the simulation. It reads and writes the seven
business databases exactly as it would in a live dealership environment.

WHAT IT DOES EACH DAY
─────────────────────
  1. Scan new / contacted leads — add a priority note to the top 3
     so salespeople know which ones to focus on first.
  2. Flag stalled CRM records (waiting, no_show) with a follow-up
     note so nothing falls through the cracks.
  3. Print a daily pipeline and P&L snapshot.

USAGE
─────
  # Start the simulation in one terminal
  .venv/bin/python main.py --reset --days 14 --seed 42

  # Run the agent in another terminal
  .venv/bin/python sample_agent.py

  # Custom poll interval or DB directory
  .venv/bin/python sample_agent.py --poll-interval 5 --db-dir ./data
"""

import argparse
import json
import os
import sqlite3
import time
from typing import Optional

# ── DB directory ──────────────────────────────────────────────────────────────
# Reads the same env var the simulation uses; can be overridden via --db-dir.
DB_DIR = os.getenv("DB_DIR", "./data")


def _db(name: str) -> str:
    """Absolute path to a named DB file."""
    return os.path.join(DB_DIR, name)


def _state_path() -> str:
    return os.path.join(DB_DIR, "simulation_state.json")


# ── Database helpers ──────────────────────────────────────────────────────────

def read_state() -> Optional[dict]:
    """
    Read simulation_state.json. Returns None if the file does not
    exist yet or contains malformed JSON — caller should retry.
    """
    try:
        with open(_state_path()) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def query(db_name: str, sql: str, params: tuple = ()) -> list[dict]:
    """
    Read-only query against a business database. Uses the SQLite URI
    'mode=ro' flag so we never accidentally lock the database.
    WAL mode means reads and writes never block each other.
    """
    conn = sqlite3.connect(f"file:{_db(db_name)}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def write_conn(db_name: str) -> sqlite3.Connection:
    """
    Open a WAL-mode write connection. Caller must commit() and close().
    """
    conn = sqlite3.connect(_db(db_name))
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ── Agent ─────────────────────────────────────────────────────────────────────

class BDManagerAgent:
    """
    Business Development Manager agent.

    Runs once per business day. Maintains in-memory sets of lead and CRM
    record IDs it has already annotated so duplicate notes are never added
    if the same records appear on consecutive days.
    """

    LEAD_STATUSES_TO_ACTION = ("new", "contacted")
    CRM_STATUSES_TO_FLAG    = ("waiting", "no_show")
    LEADS_PER_DAY           = 3   # max leads to annotate each day
    CRM_PER_DAY             = 5   # max CRM records to flag each day

    def __init__(self) -> None:
        self._noted_lead_ids: set[int] = set()
        self._noted_crm_ids:  set[int] = set()

    # ── Entry point ───────────────────────────────────────────────────────────

    def run_day(self, current_date: str) -> None:
        """Called once per day when current_date changes in simulation_state.json."""
        _banner(f"Agent — {current_date}")
        self._prioritise_leads(current_date)
        self._flag_stalled_crm(current_date)
        self._print_summary(current_date)

    # ── Task 1: lead prioritisation ───────────────────────────────────────────

    def _prioritise_leads(self, current_date: str) -> None:
        """
        Find new / contacted leads the agent hasn't annotated yet.
        Score them (contacted > new) and add a priority note to the top N.
        """
        exclusion = self._noted_lead_ids or {0}
        placeholders = ",".join("?" * len(exclusion))

        leads = query("lms.db", f"""
            SELECT id, customer_name, status, last_updated
            FROM   lms_leads
            WHERE  status IN ('new', 'contacted')
            AND    id NOT IN ({placeholders})
            ORDER BY
                CASE status WHEN 'contacted' THEN 0 ELSE 1 END,
                id ASC
            LIMIT  ?
        """, (*exclusion, self.LEADS_PER_DAY))

        if not leads:
            _info("Leads", "nothing new to prioritise")
            return

        _info("Leads", f"annotating {len(leads)} lead(s)")
        for lead in leads:
            note = (
                f"[Agent {current_date}] Priority flag — status is "
                f"'{lead['status']}'. Recommend immediate contact "
                f"to advance to 'interested' or 'scheduled'."
            )
            self._append_lead_note(lead["id"], current_date, note)
            self._noted_lead_ids.add(lead["id"])
            _detail(f"Lead #{lead['id']} ({lead['customer_name']}) "
                    f"[{lead['status']}] — note added")

    # ── Task 2: stalled CRM flagging ─────────────────────────────────────────

    def _flag_stalled_crm(self, current_date: str) -> None:
        """
        Find CRM records stuck in 'waiting' or 'no_show' that haven't
        been annotated yet. Add a follow-up reminder note.
        """
        exclusion = self._noted_crm_ids or {0}
        placeholders = ",".join("?" * len(exclusion))

        stalled = query("crm.db", f"""
            SELECT id, customer_name, status, salesperson_name,
                   car_make, car_model, car_year
            FROM   crm_records
            WHERE  status IN ('waiting', 'no_show')
            AND    id NOT IN ({placeholders})
            ORDER BY id ASC
            LIMIT  ?
        """, (*exclusion, self.CRM_PER_DAY))

        if not stalled:
            _info("CRM", "no stalled records")
            return

        _info("CRM", f"flagging {len(stalled)} stalled record(s)")
        for rec in stalled:
            car_str = (
                f"{rec['car_year']} {rec['car_make']} {rec['car_model']}"
                if rec["car_make"] else "no vehicle assigned"
            )
            note = (
                f"[Agent {current_date}] Stalled in '{rec['status']}' — "
                f"vehicle: {car_str}. "
                f"Assigned to {rec['salesperson_name'] or 'unassigned'}. "
                f"Recommend personal outreach within 24 hours."
            )
            self._append_crm_note(rec["id"], current_date, note)
            self._noted_crm_ids.add(rec["id"])
            _detail(f"CRM #{rec['id']} ({rec['customer_name']}) "
                    f"[{rec['status']}] — flagged")

    # ── Task 3: daily snapshot ────────────────────────────────────────────────

    def _print_summary(self, current_date: str) -> None:
        """Print a pipeline and P&L snapshot queried from the business databases."""

        # Sales closed today (from CRM)
        sales_today = query("crm.db",
            "SELECT customer_name, sale_price FROM crm_records "
            "WHERE status = 'sold' AND meeting_date = ?",
            (current_date,))

        # New leads seen today (from LMS)
        new_leads_today = query("lms.db",
            "SELECT COUNT(*) AS n FROM lms_leads WHERE last_updated = ?",
            (current_date,))
        leads_count = new_leads_today[0]["n"] if new_leads_today else 0

        # LMS pipeline totals
        pipeline = query("lms.db",
            "SELECT status, COUNT(*) AS n FROM lms_leads GROUP BY status")
        pipeline_map = {r["status"]: r["n"] for r in pipeline}

        # CRM pipeline totals
        crm_snap = query("crm.db",
            "SELECT status, COUNT(*) AS n FROM crm_records GROUP BY status")
        crm_map = {r["status"]: r["n"] for r in crm_snap}

        # Available inventory (from DMS)
        inv = query("dms.db",
            "SELECT COUNT(*) AS n FROM dms_cars WHERE status = 'available'")

        # Running P&L (from ERP)
        pnl = query("erp.db",
            "SELECT transaction_type, SUM(amount) AS total "
            "FROM erp_transactions GROUP BY transaction_type")
        pnl_map = {r["transaction_type"]: float(r["total"] or 0) for r in pnl}
        revenue  = pnl_map.get("credit", 0.0)
        expenses = pnl_map.get("debit",  0.0)

        # Active loan portfolio (from LSS)
        loans = query("lss.db",
            "SELECT COUNT(*) AS n, "
            "COALESCE(SUM(payment_amount * payments_left), 0) AS portfolio "
            "FROM lss_loans WHERE payments_left > 0")

        print()
        print("  ┌─ TODAY ─────────────────────────────────────────────┐")
        print(f"  │  Sales closed:    {len(sales_today):>3}                              │")
        print(f"  │  Leads active:    {leads_count:>3}                              │")
        print("  ├─ PIPELINE (cumulative) ─────────────────────────────┤")
        print(f"  │  LMS new:         {pipeline_map.get('new', 0):>4}  "
              f"contacted: {pipeline_map.get('contacted', 0):>4}  "
              f"interested: {pipeline_map.get('interested', 0):>3}  │")
        print(f"  │  LMS scheduled:   {pipeline_map.get('scheduled', 0):>4}  "
              f"met: {pipeline_map.get('met', 0):>4}                          │")
        print(f"  │  CRM in_neg:      {crm_map.get('in_negotiation', 0):>4}  "
              f"waiting: {crm_map.get('waiting', 0):>4}  "
              f"sold: {crm_map.get('sold', 0):>4}     │")
        print(f"  │  Inventory:       {inv[0]['n']:>4} cars available                  │")
        print(f"  │  Loan portfolio:  ${float(loans[0]['portfolio']):>12,.0f}                  │")
        print("  ├─ P&L (all time) ────────────────────────────────────┤")
        print(f"  │  Revenue:   ${revenue:>14,.0f}                         │")
        print(f"  │  Expenses:  ${expenses:>14,.0f}                         │")
        print(f"  │  Net:       ${revenue - expenses:>14,.0f}                         │")
        print("  └─────────────────────────────────────────────────────┘")

    # ── DB write helpers ──────────────────────────────────────────────────────

    def _append_lead_note(self, lead_id: int, current_date: str, text: str) -> None:
        """Append a JSON note entry to lms_leads.notes."""
        conn = write_conn("lms.db")
        row = conn.execute(
            "SELECT notes FROM lms_leads WHERE id = ?", (lead_id,)
        ).fetchone()
        if row:
            notes = json.loads(row[0] or "[]")
            notes.append({"date": current_date, "text": text})
            conn.execute(
                "UPDATE lms_leads SET notes = ?, last_updated = ? WHERE id = ?",
                (json.dumps(notes), current_date, lead_id)
            )
            conn.commit()
        conn.close()

    def _append_crm_note(self, record_id: int, current_date: str, text: str) -> None:
        """Append a JSON note entry to crm_records.notes."""
        conn = write_conn("crm.db")
        row = conn.execute(
            "SELECT notes FROM crm_records WHERE id = ?", (record_id,)
        ).fetchone()
        if row:
            notes = json.loads(row[0] or "[]")
            notes.append({"date": current_date, "text": text})
            conn.execute(
                "UPDATE crm_records SET notes = ? WHERE id = ?",
                (json.dumps(notes), record_id)
            )
            conn.commit()
        conn.close()


# ── Polling loop ──────────────────────────────────────────────────────────────

def run_agent(agent: BDManagerAgent, poll_interval: float) -> None:
    """
    Poll simulation_state.json every `poll_interval` seconds.
    When current_date changes, run the agent for that day.
    """
    print(f"Agent started — polling every {poll_interval}s for a new day.")
    print("Start the simulation in another terminal if it isn't running, e.g.:")
    print("  .venv/bin/python main.py --reset --days 14 --seed 42\n")

    last_date: Optional[str] = None

    while True:
        state = read_state()

        if state is None:
            time.sleep(poll_interval)
            continue

        if state["status"] == "completed":
            print("\nRun complete — agent shutting down.")
            break

        current_date = state["current_date"]

        if current_date != last_date:
            agent.run_day(current_date)
            last_date = current_date

        time.sleep(poll_interval)


# ── Output helpers ────────────────────────────────────────────────────────────

def _banner(msg: str) -> None:
    width = 60
    print(f"\n{'═' * width}")
    print(f"  {msg}")
    print(f"{'═' * width}")


def _info(section: str, msg: str) -> None:
    print(f"  [{section}] {msg}")


def _detail(msg: str) -> None:
    print(f"      {msg}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Main Street Motors — BD Manager sample agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--poll-interval", type=float, default=3.0,
        help="Seconds between checks of simulation_state.json (default: 3)",
    )
    p.add_argument(
        "--db-dir", default=None,
        help="Override DB directory (default: $DB_DIR or ./data)",
    )
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.db_dir:
        global DB_DIR
        DB_DIR = args.db_dir

    agent = BDManagerAgent()
    run_agent(agent, poll_interval=args.poll_interval)


if __name__ == "__main__":
    main()
