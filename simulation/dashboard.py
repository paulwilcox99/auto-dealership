"""Live dashboard for simulation progress."""

from contextlib import contextmanager
from datetime import date
from typing import Optional

from rich.columns import Columns
from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TaskID, TextColumn
from rich.table import Table
from rich.text import Text

from simulation.console import sim_console

_STAT_LABELS = [
    ("new_leads",        "New Leads"),
    ("leads_processed",  "Leads Processed"),
    ("cars_acquired",    "Cars Acquired"),
    ("cars_sold",        "Cars Sold"),
    ("cash_deals",       "Cash Deals"),
    ("loans",            "Loan Deals"),
    ("total_revenue",    "Revenue"),
    ("total_car_costs",  "Inventory Cost"),
    ("total_salaries",   "Payroll"),
]

_CURRENCY_KEYS = {"total_revenue", "total_salaries"}


def _fmt(key: str, value) -> str:
    if key in _CURRENCY_KEYS:
        return f"${value:,.0f}"
    return str(int(value))


class LiveDashboard:
    def __init__(self, total_days: int, start_date: date) -> None:
        self._total_days = total_days
        self._start_date = start_date
        self._day_number: int = 0
        self._current_date: Optional[date] = None
        self._daily_stats: dict = {}
        self._cumulative_stats: dict = {}
        self._current_worker: Optional[str] = None
        self._last_worker: Optional[str] = None
        self._live: Optional[Live] = None

        self._progress = Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=22),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=sim_console,
        )
        self._progress_task: Optional[TaskID] = None

    # ------------------------------------------------------------------
    def _build_panel(self) -> Panel:
        # Progress row
        day_label = (
            f"Day {self._day_number} / {self._total_days}"
            if self._day_number
            else f"Day — / {self._total_days}"
        )
        if self._progress_task is not None:
            self._progress.update(self._progress_task, description=day_label)

        date_line = (
            f"  {self._current_date}  {self._current_date.strftime('%A')}"
            if self._current_date
            else ""
        )

        # Two-column stats table
        grid = Table.grid(expand=True)
        grid.add_column(justify="left", ratio=1)
        grid.add_column(justify="left", ratio=1)

        # Header row
        grid.add_row(
            Text("  TODAY", style="bold cyan"),
            Text("  CUMULATIVE", style="bold cyan"),
        )
        grid.add_row("", "")  # blank separator

        for key, label in _STAT_LABELS:
            today_val = _fmt(key, self._daily_stats.get(key, 0))
            cum_val   = _fmt(key, self._cumulative_stats.get(key, 0))
            grid.add_row(
                f"  {label:<20} {today_val}",
                f"  {label:<20} {cum_val}",
            )

        # Footer line
        if self._current_worker:
            footer = Text(f"\n  Running: {self._current_worker}", style="dim")
        elif self._last_worker:
            footer = Text(f"\n  Last completed: {self._last_worker}", style="dim")
        else:
            footer = Text("")

        content = Group(
            self._progress,
            Text(date_line),
            Text(""),
            grid,
            footer,
        )

        return Panel(content, title="[bold]MAIN STREET MOTORS[/bold]", border_style="blue")

    # ------------------------------------------------------------------
    def __enter__(self) -> "LiveDashboard":
        self._progress_task = self._progress.add_task(
            f"Day — / {self._total_days}", total=self._total_days
        )
        self._live = Live(
            self._build_panel(),
            console=sim_console,
            refresh_per_second=4,
            redirect_stdout=False,
            redirect_stderr=False,
        )
        self._live.__enter__()
        return self

    def __exit__(self, *args) -> None:
        if self._live:
            self._live.__exit__(*args)

    # ------------------------------------------------------------------
    def set_current_worker(self, name: str) -> None:
        self._current_worker = name
        self._last_worker = None
        if self._live:
            self._live.update(self._build_panel())

    def set_last_worker(self, name: str) -> None:
        self._last_worker = name
        self._current_worker = None
        if self._live:
            self._live.update(self._build_panel())

    def update(
        self,
        day_number: int,
        current_date: date,
        daily_stats: dict,
        cumulative_stats: dict,
    ) -> None:
        self._day_number = day_number
        self._current_date = current_date
        self._daily_stats = daily_stats
        self._cumulative_stats = cumulative_stats
        if self._progress_task is not None:
            self._progress.update(self._progress_task, completed=day_number)
        if self._live:
            self._live.update(self._build_panel())
