"""Day loop: scheduling logic and step mode."""

import random
from datetime import date, timedelta
from typing import List

from rich.console import Console
from rich.panel import Panel

from config import (
    LEAD_CREATION_INTERVAL, SALES_FOLLOWUP_INTERVAL, NEW_CARS_INTERVAL,
)
from simulation.state import write_state
from workers import get_worker_instances, WORKER_NAMES

console = Console()


def _should_run(worker_name: str, sim_date: date, start_date: date, day_number: int) -> bool:
    """Return True if the worker should execute on this day."""
    weekday = sim_date.weekday()  # 0=Mon … 6=Sun
    is_weekday = weekday < 5
    is_friday = weekday == 4
    is_first_of_month = sim_date.day == 1

    delta = (sim_date - start_date).days

    schedule = {
        "lead_creation": delta % LEAD_CREATION_INTERVAL == 0,
        "lead_processing": is_weekday,
        "schedule_lead": is_weekday,
        "walk_ins": True,
        "sales_meeting": True,
        "sales_followup": delta > 0 and delta % SALES_FOLLOWUP_INTERVAL == 0,
        "new_cars": delta > 0 and delta % NEW_CARS_INTERVAL == 0,
        "finance_sales": True,
        "finance_payments": is_first_of_month,
        "payday": is_friday,
    }
    return schedule.get(worker_name, False)


def run_loop(
    start_date: date,
    end_date: date,
    rng: random.Random,
    enabled_workers: List[str],
    disabled_workers: List[str],
    step_mode: bool = False,
    dashboard: bool = False,
    verbose: bool = True,
    seed: int = 0,
) -> None:
    """Main simulation day loop."""
    from reporting.reporter import Reporter
    reporter = Reporter(start_date=start_date, end_date=end_date)

    workers = get_worker_instances(enabled_workers)
    total_days = (end_date - start_date).days
    current_date = start_date

    day_number = 0
    while current_date < end_date:
        day_number += 1
        weekday_name = current_date.strftime("%A")

        console.print(Panel(
            f"[bold]Day {day_number} | {current_date} ({weekday_name})[/bold]",
            style="bold blue",
        ))

        write_state(
            status="running",
            current_date=current_date,
            start_date=start_date,
            end_date=end_date,
            day_number=day_number,
            total_days=total_days,
            last_completed_worker=None,
            workers_enabled=enabled_workers,
            workers_disabled=disabled_workers,
        )

        daily_stats: dict = {
            "cars_sold": 0,
            "new_leads": 0,
            "leads_processed": 0,
            "cash_deals": 0,
            "loans": 0,
            "total_employees": 0,
            "total_revenue": 0.0,
            "total_car_costs": 0.0,
            "total_salaries": 0.0,
        }

        last_worker = None
        for worker in workers:
            if not _should_run(worker.name, current_date, start_date, day_number):
                continue

            result = worker.run(sim_date=current_date, rng=rng)
            if result:
                for k, v in result.items():
                    if k in daily_stats:
                        daily_stats[k] = daily_stats[k] + v

            last_worker = worker.name
            write_state(
                status="running",
                current_date=current_date,
                start_date=start_date,
                end_date=end_date,
                day_number=day_number,
                total_days=total_days,
                last_completed_worker=last_worker,
                workers_enabled=enabled_workers,
                workers_disabled=disabled_workers,
            )

        reporter.record_day(current_date, daily_stats)

        if step_mode:
            write_state(
                status="paused",
                current_date=current_date,
                start_date=start_date,
                end_date=end_date,
                day_number=day_number,
                total_days=total_days,
                last_completed_worker=last_worker,
                workers_enabled=enabled_workers,
                workers_disabled=disabled_workers,
            )
            try:
                input("\n[step-mode] Press [Enter] to advance to next day...")
            except EOFError:
                pass
            write_state(
                status="running",
                current_date=current_date,
                start_date=start_date,
                end_date=end_date,
                day_number=day_number,
                total_days=total_days,
                last_completed_worker=last_worker,
                workers_enabled=enabled_workers,
                workers_disabled=disabled_workers,
            )

        current_date += timedelta(days=1)

    # Simulation complete
    write_state(
        status="completed",
        current_date=end_date,
        start_date=start_date,
        end_date=end_date,
        day_number=day_number,
        total_days=total_days,
        last_completed_worker=last_worker if 'last_worker' in dir() else None,
        workers_enabled=enabled_workers,
        workers_disabled=disabled_workers,
    )

    reporter.print_final_report()
