"""CLI entry point and simulation orchestration."""

import argparse
import os
import random
import sys
from datetime import date, timedelta

from dotenv import load_dotenv
from rich.console import Console

load_dotenv()

console = Console()

# ── CLI argument parsing ──────────────────────────────────────────────────────

def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Main Street Motors — Dealership Simulation",
    )
    parser.add_argument(
        "--days", type=int, default=30,
        help="Number of simulation days to run (default: 30)",
    )
    parser.add_argument(
        "--start-date", type=str, default=None,
        help="Simulation start date YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--step-mode", action="store_true",
        help="Pause after each day and wait for [Enter]",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Drop and re-initialize all databases before running",
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="Random seed for reproducible simulations",
    )
    parser.add_argument(
        "--disable-workers", type=str, default="",
        help="Comma-separated list of worker names to disable",
    )
    parser.add_argument(
        "--disable-all-workers", action="store_true",
        help="Disable all workers (external scripts handle everything)",
    )
    parser.add_argument(
        "--dashboard", action="store_true",
        help="Show live Rich dashboard during simulation",
    )
    parser.add_argument(
        "--db-dir", type=str, default=None,
        help="Override DB directory path",
    )
    parser.add_argument(
        "--verbose", action="store_true", default=True,
        help="Verbose per-worker output (default: on)",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    # ── Override DB_DIR if provided ───────────────────────────────────────────
    if args.db_dir:
        import config
        config.DB_DIR = args.db_dir
        os.environ["DB_DIR"] = args.db_dir

    # ── Import after possible DB_DIR override ─────────────────────────────────
    from config import DB_DIR
    from simulation.state import write_state, read_state
    from initialization.seeder import run_seeder, ALL_DBS

    # ── Dates ─────────────────────────────────────────────────────────────────
    if args.start_date:
        try:
            start_date = date.fromisoformat(args.start_date)
        except ValueError:
            console.print(f"[red]Invalid --start-date format: {args.start_date!r}. Use YYYY-MM-DD.[/red]")
            sys.exit(1)
    else:
        start_date = date.today()

    end_date = start_date + timedelta(days=args.days)

    # ── Random seed ───────────────────────────────────────────────────────────
    seed = args.seed
    if seed is None:
        seed = random.randint(0, 2**31)
    rng = random.Random(seed)
    console.print(f"[dim]Random seed: {seed}[/dim]")

    # ── Determine disabled workers ─────────────────────────────────────────────
    from workers import WORKER_NAMES
    cli_disabled: set[str] = set()
    if args.disable_all_workers:
        cli_disabled = set(WORKER_NAMES)
    elif args.disable_workers:
        cli_disabled = {w.strip() for w in args.disable_workers.split(",") if w.strip()}

    # Also check .env DISABLE_WORKER_<NAME>=true
    env_disabled: set[str] = set()
    for name in WORKER_NAMES:
        env_key = f"DISABLE_WORKER_{name.upper()}"
        if os.getenv(env_key, "").lower() == "true":
            env_disabled.add(name)

    disabled_workers = cli_disabled | env_disabled
    enabled_workers = [w for w in WORKER_NAMES if w not in disabled_workers]

    # ── Init / reset ──────────────────────────────────────────────────────────
    needs_init = args.reset
    if not needs_init:
        # Check if DBs exist
        any_missing = any(
            not os.path.exists(os.path.join(DB_DIR, db))
            for db in ALL_DBS
        )
        if any_missing:
            needs_init = True
            console.print("[yellow]No existing databases found — running initialization.[/yellow]")

    if needs_init:
        run_seeder(rng=rng, start_date=start_date, end_date=end_date)

    # ── Run simulation loop ───────────────────────────────────────────────────
    from simulation.loop import run_loop
    run_loop(
        start_date=start_date,
        end_date=end_date,
        rng=rng,
        enabled_workers=enabled_workers,
        disabled_workers=list(disabled_workers),
        step_mode=args.step_mode,
        dashboard=args.dashboard,
        verbose=args.verbose,
        seed=seed,
    )


if __name__ == "__main__":
    main()
