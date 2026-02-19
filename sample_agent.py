"""
sample_agent.py — Main Street Motors BD Manager Agent

Demonstrates both sync patterns from docs/agent_developer_guide.md.

MODES
─────
  --step      Launch the simulation as a subprocess (--step-mode).
              The agent runs after every day before the sim advances.
              Guarantees exclusive DB access during agent turn.

  --free-run  Assume the simulation is already running in another
              terminal. Polls simulation_state.json for day changes.

WHAT IT DOES EACH DAY
─────────────────────
  1. Scan new / contacted leads — add a priority note to the top 3
     so salespeople know which ones to focus on first.
  2. Flag stalled CRM records (waiting, no_show) with a follow-up
     note so nothing falls through the cracks.
  3. Print a daily P&L and pipeline snapshot.
  4. Write a summary event to events.db so the agent's activity is
     visible alongside simulation events.

USAGE
─────
  # Step mode — agent controls the sim, processes every day
  .venv/bin/python sample_agent.py --step --days 14 --seed 42

  # Free-run mode — start sim separately, agent tails it
  .venv/bin/python main.py --reset --days 14 --seed 42 &
  .venv/bin/python sample_agent.py --free-run

  # Optional: slow the sim down so you can watch both processes
  .venv/bin/python sample_agent.py --step --days 14 --seed 42 --day-pause 1.5
"""

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from typing import Optional

# ── Resolve DB_DIR ────────────────────────────────────────────────────────────
# Honour the same env var the simulation uses.  Can also be overridden
# by --db-dir on the CLI (applied before any DB access).
DB_DIR = os.getenv("DB_DIR", "./data")


def _db(name: str) -> str:
    """Absolute path to a named DB file."""
    return os.path.join(DB_DIR, name)


def _state_path() -> str:
    return os.path.join(DB_DIR, "simulation_state.json")


# ── Low-level DB helpers ──────────────────────────────────────────────────────

def read_state() -> Optional[dict]:
    """
    Read simulation_state.json.  Returns None if the file does not
    exist yet or contains malformed JSON (retry on next poll).
    """
    try:
        with open(_state_path()) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def query(db_name: str, sql: str, params: tuple = ()) -> list[dict]:
    """
    Read-only query against any DB.  Uses the SQLite URI 'mode=ro'
    flag so we never accidentally lock out the simulation.
    WAL mode means the sim can write simultaneously without blocking.
    """
    conn = sqlite3.connect(f"file:{_db(db_name)}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def write(db_name: str, sql: str, params: tuple = ()) -> None:
    """
    Single-statement write to a DB.  Always enables WAL so concurrent
    reads (by the sim or other agents) are unaffected.
    """
    conn = sqlite3.connect(_db(db_name))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(sql, params)
    conn.commit()
    conn.close()


def write_conn(db_name: str) -> sqlite3.Connection:
    """
    Return an open WAL-mode connection for multi-statement writes.
    Caller must commit() and close() when done.
    """
    conn = sqlite3.connect(_db(db_name))
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ── Agent class ───────────────────────────────────────────────────────────────

class BDManagerAgent:
    """
    Business Development Manager agent.

    Runs once per simulated day.  Maintains in-memory sets of lead and
    CRM record IDs it has already annotated so duplicate notes are never
    added if the same records appear on consecutive days.
    """

    LEAD_STATUSES_TO_ACTION = ("new", "contacted")
    CRM_STATUSES_TO_FLAG    = ("waiting", "no_show")
    LEADS_PER_DAY           = 3   # max leads to annotate each day
    CRM_PER_DAY             = 5   # max CRM records to flag each day

    def __init__(self) -> None:
        self._noted_lead_ids: set[int] = set()
        self._noted_crm_ids:  set[int] = set()
        self._days_run = 0

    # ── Entry point ───────────────────────────────────────────────────────────

    def run_day(self, sim_date: str, day_number: int) -> None:
        """Called once per simulated day after all workers have completed."""
        self._days_run += 1
        _banner(f"Agent — Day {day_number}  ({sim_date})")

        self._prioritise_leads(sim_date)
        self._flag_stalled_crm(sim_date)
        self._print_summary(sim_date, day_number)

    # ── Task 1: lead prioritisation ───────────────────────────────────────────

    def _prioritise_leads(self, sim_date: str) -> None:
        """
        Find new / contacted leads the agent hasn't seen yet.
        Score them (contacted > new, acts as a simple triage) and add a
        priority note to the top N so salespeople know where to focus.
        """
        # Build exclusion list — skip leads already annotated
        exclusion = self._noted_lead_ids or {0}   # {0} → no real IDs excluded
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
                f"[Agent {sim_date}] Priority flag — status is "
                f"'{lead['status']}'. Recommend immediate contact "
                f"to advance to 'interested' or 'scheduled'."
            )
            self._append_lead_note(lead["id"], sim_date, note)
            self._noted_lead_ids.add(lead["id"])
            _detail(f"Lead #{lead['id']} ({lead['customer_name']}) "
                    f"[{lead['status']}] — note added")

    # ── Task 2: stalled CRM flagging ─────────────────────────────────────────

    def _flag_stalled_crm(self, sim_date: str) -> None:
        """
        Find CRM records stuck in 'waiting' or 'no_show' that the agent
        has not yet annotated.  Add a follow-up reminder note.
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
                f"[Agent {sim_date}] Stalled in '{rec['status']}' — "
                f"vehicle: {car_str}. "
                f"Assigned to {rec['salesperson_name'] or 'unassigned'}. "
                f"Recommend personal outreach within 24 hours."
            )
            self._append_crm_note(rec["id"], sim_date, note)
            self._noted_crm_ids.add(rec["id"])
            _detail(f"CRM #{rec['id']} ({rec['customer_name']}) "
                    f"[{rec['status']}] — flagged")

    # ── Task 3: daily snapshot ────────────────────────────────────────────────

    def _print_summary(self, sim_date: str, day_number: int) -> None:
        """Print a pipeline + P&L snapshot and log it to events.db."""

        # Events that fired today
        todays_events = query("events.db",
            "SELECT action, amount FROM events WHERE sim_date = ?", (sim_date,))
        sales_today   = [e for e in todays_events if e["action"] == "sale"]
        leads_today   = [e for e in todays_events if e["action"] == "create"]
        payroll_today = [e for e in todays_events if e["action"] == "payroll"]

        # Pipeline snapshot (cumulative)
        pipeline = query("lms.db", """
            SELECT status, COUNT(*) AS n FROM lms_leads GROUP BY status
        """)
        pipeline_map = {r["status"]: r["n"] for r in pipeline}

        crm_snap = query("crm.db", """
            SELECT status, COUNT(*) AS n FROM crm_records GROUP BY status
        """)
        crm_map = {r["status"]: r["n"] for r in crm_snap}

        # Inventory
        inv = query("dms.db",
            "SELECT COUNT(*) AS n FROM dms_cars WHERE status = 'available'")

        # Running P&L from ERP
        pnl = query("erp.db", """
            SELECT transaction_type, SUM(amount) AS total
            FROM   erp_transactions
            GROUP BY transaction_type
        """)
        pnl_map = {r["transaction_type"]: float(r["total"] or 0) for r in pnl}
        revenue  = pnl_map.get("credit", 0)
        expenses = pnl_map.get("debit",  0)

        # Active loans
        loans = query("lss.db", """
            SELECT COUNT(*) AS n,
                   COALESCE(SUM(payment_amount * payments_left), 0) AS portfolio
            FROM lss_loans WHERE payments_left > 0
        """)

        print()
        print("  ┌─ TODAY ─────────────────────────────────────────────┐")
        print(f"  │  Sales closed:    {len(sales_today):>3}                              │")
        print(f"  │  New leads:       {len(leads_today):>3}                              │")
        if payroll_today:
            pay_amt = sum(float(e["amount"] or 0) for e in payroll_today)
            print(f"  │  Payroll run:     ${pay_amt:>12,.0f}                  │")
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

        # Log summary to events.db
        description = (
            f"Day {day_number}: {len(sales_today)} sales, "
            f"{len(leads_today)} new leads, "
            f"{pipeline_map.get('interested', 0)} interested leads, "
            f"{inv[0]['n']} cars in stock, "
            f"net P&L ${revenue - expenses:,.0f}"
        )
        write("events.db",
            "INSERT INTO events "
            "(sim_date, sim_timestamp, worker_name, action, description) "
            "VALUES (?, ?, 'agent', 'daily_summary', ?)",
            (sim_date, datetime.utcnow().isoformat() + "Z", description))

    # ── DB write helpers ──────────────────────────────────────────────────────

    def _append_lead_note(self, lead_id: int, sim_date: str, text: str) -> None:
        """Append a JSON note entry to lms_leads.notes for the given lead."""
        conn = write_conn("lms.db")
        row = conn.execute(
            "SELECT notes FROM lms_leads WHERE id = ?", (lead_id,)
        ).fetchone()
        if row:
            notes = json.loads(row[0] or "[]")
            notes.append({"date": sim_date, "text": text})
            conn.execute(
                "UPDATE lms_leads SET notes = ?, last_updated = ? WHERE id = ?",
                (json.dumps(notes), sim_date, lead_id)
            )
            conn.commit()
        conn.close()

    def _append_crm_note(self, record_id: int, sim_date: str, text: str) -> None:
        """Append a JSON note entry to crm_records.notes for the given record."""
        conn = write_conn("crm.db")
        row = conn.execute(
            "SELECT notes FROM crm_records WHERE id = ?", (record_id,)
        ).fetchone()
        if row:
            notes = json.loads(row[0] or "[]")
            notes.append({"date": sim_date, "text": text})
            conn.execute(
                "UPDATE crm_records SET notes = ? WHERE id = ?",
                (json.dumps(notes), record_id)
            )
            conn.commit()
        conn.close()


# ── Sync: free-running mode ───────────────────────────────────────────────────

def run_free(agent: BDManagerAgent, day_pause: float) -> None:
    """
    Poll simulation_state.json for date changes.
    The simulation must already be running in another terminal.

    day_pause — optional minimum seconds to wait after reacting to each day
                before polling again.  Useful if you want to slow things down
                to watch both processes.
    """
    print("Free-run mode — waiting for simulation...")
    print("Start the sim in another terminal, e.g.:")
    print("  .venv/bin/python main.py --reset --days 14 --seed 42\n")

    last_date: Optional[str] = None

    while True:
        state = _wait_for_new_day(last_date)

        if state["status"] == "completed":
            print("\nSimulation complete — agent shutting down.")
            break

        agent.run_day(state["current_date"], state["day_number"])
        last_date = state["current_date"]

        if day_pause > 0:
            time.sleep(day_pause)


def _wait_for_new_day(known_date: Optional[str],
                      poll_interval: float = 0.25) -> dict:
    """
    Block until state file shows a date different from known_date
    OR status == 'completed'.
    """
    while True:
        state = read_state()
        if state is None:
            time.sleep(poll_interval)
            continue
        if state["status"] == "completed":
            return state
        # A new day has started when either:
        #   (a) we have no previous date yet, or
        #   (b) the date in the file has advanced
        # We wait until the day is at least partially complete — specifically
        # until the state file shows a last_completed_worker (meaning at
        # least one worker has run), to avoid reacting to the very start
        # of a day before any DB writes have happened.
        if (state["current_date"] != known_date
                and state.get("last_completed_worker") is not None):
            # Wait a beat for the final worker to commit its writes
            time.sleep(0.1)
            return state
        time.sleep(poll_interval)


# ── Sync: step-by-step mode ───────────────────────────────────────────────────

def run_step(agent: BDManagerAgent, days: int, seed: int,
             day_pause: float, extra_args: list) -> None:
    """
    Launch the simulation as a subprocess with --step-mode, then control
    its stdin to advance day-by-day.

    After each day the simulation writes status='paused' and blocks on
    stdin.  We detect that, run the agent, then send a newline to advance.

    Timing guarantee: when status='paused' all 10 workers for that day
    have committed their DB writes.  The sim will not touch any DB until
    we send the newline, so the agent has effectively exclusive write
    access during its turn.
    """
    cmd = [
        sys.executable, "main.py",
        "--reset",
        f"--days={days}",
        f"--seed={seed}",
        "--step-mode",
    ] + extra_args

    print(f"Launching simulation: {' '.join(cmd)}\n")

    # Inherit stdout/stderr so simulation output is visible; capture stdin.
    sim = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    try:
        while True:
            # ── Wait for sim to finish a day ──────────────────────────────
            state = _wait_for_status("paused", timeout=120.0)

            if state is None:
                # Sim may have finished (no more days) without pausing
                if sim.poll() is not None:
                    print("\nSimulation process exited.")
                    break
                print("ERROR: timed out waiting for 'paused' status.")
                break

            # ── Run agent logic ───────────────────────────────────────────
            agent.run_day(state["current_date"], state["day_number"])

            if day_pause > 0:
                time.sleep(day_pause)

            # ── Advance the simulation ────────────────────────────────────
            print(f"\n  → Advancing to day {state['day_number'] + 1}…")
            sim.stdin.write(b"\n")
            sim.stdin.flush()

            # Brief pause to let the sim transition from 'paused' → 'running'
            # before our next poll so we don't latch onto the old 'paused' state
            time.sleep(0.2)

            # Check for normal completion
            final = read_state()
            if final and final["status"] == "completed":
                # Let reporter finish printing, then we're done
                sim.wait()
                print("\nSimulation complete — agent shutting down.")
                break

    finally:
        try:
            sim.stdin.close()
        except Exception:
            pass
        if sim.poll() is None:
            sim.wait()


def _wait_for_status(target: str, timeout: float) -> Optional[dict]:
    """Poll state file until status matches target, or timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = read_state()
        if state and state["status"] == target:
            return state
        time.sleep(0.1)
    return None


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
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--step",
        action="store_true",
        help="Launch sim as a subprocess and step through each day",
    )
    mode.add_argument(
        "--free-run",
        action="store_true",
        help="Poll a simulation that is already running separately",
    )
    p.add_argument("--days",      type=int,   default=14,
                   help="Days to simulate (step mode only, default: 14)")
    p.add_argument("--seed",      type=int,   default=42,
                   help="Random seed (step mode only, default: 42)")
    p.add_argument("--day-pause", type=float, default=0.0,
                   help="Seconds to pause after each day reaction (default: 0)")
    p.add_argument("--db-dir",    default=None,
                   help="Override DB directory (default: $DB_DIR or ./data)")
    return p


def main() -> None:
    parser = build_parser()
    args, extra_args = parser.parse_known_args()

    # Apply DB_DIR override before any DB access
    if args.db_dir:
        global DB_DIR
        DB_DIR = args.db_dir
        os.environ["DB_DIR"] = args.db_dir

    agent = BDManagerAgent()

    if args.step:
        run_step(agent,
                 days=args.days,
                 seed=args.seed,
                 day_pause=args.day_pause,
                 extra_args=extra_args)
    else:
        run_free(agent, day_pause=args.day_pause)


if __name__ == "__main__":
    main()
