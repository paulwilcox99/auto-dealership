"""Daily verbose log, Results DB writes, and final end-of-simulation report."""

import os
from datetime import date
from decimal import Decimal
from typing import List

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from config import DB_DIR
from database.session import session_for
from models.sim_models import SimResult

console = Console()
SIM_RESULT_DB = "sim_results.db"


class Reporter:
    """Collects daily stats, writes to sim_results.db, and prints final report."""

    def __init__(self, start_date: date, end_date: date):
        self.start_date = start_date
        self.end_date = end_date
        self.daily_records: List[dict] = []

    def record_day(self, sim_date: date, stats: dict) -> None:
        """Persist a daily snapshot to sim_results.db."""
        session = session_for(SIM_RESULT_DB)
        result = SimResult(
            sim_date=sim_date,
            cars_sold=stats.get("cars_sold", 0),
            cars_acquired=stats.get("cars_acquired", 0),
            new_leads=stats.get("new_leads", 0),
            leads_processed=stats.get("leads_processed", 0),
            cash_deals=stats.get("cash_deals", 0),
            loans=stats.get("loans", 0),
            total_employees=stats.get("total_employees", 0),
            total_revenue=Decimal(str(stats.get("total_revenue", 0))),
            total_car_costs=Decimal(str(stats.get("total_car_costs", 0))),
            total_salaries=Decimal(str(stats.get("total_salaries", 0))),
        )
        session.add(result)
        session.commit()
        session.close()
        self.daily_records.append({"date": sim_date, **stats})

    def print_final_report(self) -> None:
        """Print and save the end-of-simulation summary."""
        if not self.daily_records:
            console.print("[yellow]No data to report.[/yellow]")
            return

        # Aggregate
        total_sold = sum(d.get("cars_sold", 0) for d in self.daily_records)
        total_acquired = sum(d.get("cars_acquired", 0) for d in self.daily_records)
        total_cash = sum(d.get("cash_deals", 0) for d in self.daily_records)
        total_loans = sum(d.get("loans", 0) for d in self.daily_records)
        total_leads = sum(d.get("new_leads", 0) for d in self.daily_records)
        total_revenue = sum(d.get("total_revenue", 0) for d in self.daily_records)
        total_salaries = sum(d.get("total_salaries", 0) for d in self.daily_records)
        total_car_costs = sum(d.get("total_car_costs", 0) for d in self.daily_records)
        days = len(self.daily_records)

        net_profit = total_revenue - total_salaries - total_car_costs

        # Get loan portfolio value from LSS
        loan_portfolio = 0.0
        try:
            from database.session import session_for as sf
            lss_session = sf("lss.db")
            from models.company_models import LSSLoan
            loans_active = lss_session.query(LSSLoan).filter(LSSLoan.payments_left > 0).all()
            for loan in loans_active:
                remaining = float(loan.payments_left or 0) * float(loan.payment_amount or 0)
                loan_portfolio += remaining
            lss_session.close()
        except Exception:
            pass

        # Top-selling cars
        car_counts: dict = {}
        try:
            dms_session = session_for("dms.db")
            from models.company_models import DMSCar
            sold_cars = dms_session.query(DMSCar).filter_by(status="sold").all()
            for car in sold_cars:
                key = f"{car.make} {car.model}"
                car_counts[key] = car_counts.get(key, 0) + 1
            dms_session.close()
        except Exception:
            pass

        top_cars = sorted(car_counts.items(), key=lambda x: x[1], reverse=True)[:5]

        # Build report text
        lines = [
            f"Main Street Motors — Simulation Report",
            f"Period: {self.start_date} → {self.end_date}  ({days} days)",
            "",
            f"SALES",
            f"  Total cars sold:        {total_sold}",
            f"  Cars acquired:          {total_acquired}",
            f"  Cash deals:             {total_cash}",
            f"  Loan deals:             {total_loans}",
            f"  Total revenue:          ${total_revenue:,.2f}",
            "",
            f"LEADS",
            f"  New leads created:      {total_leads}",
            "",
            f"FINANCIALS",
            f"  Total payroll expense:  ${total_salaries:,.2f}",
            f"  Total car costs:        ${total_car_costs:,.2f}",
            f"  Net profit estimate:    ${net_profit:,.2f}",
            f"  Active loan portfolio:  ${loan_portfolio:,.2f}",
            "",
            f"DAILY AVERAGES",
            f"  Cars sold/day:          {total_sold/days:.2f}",
            f"  Revenue/day:            ${total_revenue/days:,.2f}",
            f"  Leads/day:              {total_leads/days:.2f}",
            "",
        ]
        if top_cars:
            lines.append("TOP-SELLING MODELS")
            for model, count in top_cars:
                lines.append(f"  {model:30s} {count}")

        report_text = "\n".join(lines)

        # Print to console
        console.print(Panel(report_text, title="[bold green]End-of-Simulation Report[/bold green]", expand=False))

        # Save to file
        filename = f"sim_report_{self.start_date}_{self.end_date}.txt"
        report_path = os.path.join(DB_DIR, filename)
        try:
            with open(report_path, "w") as f:
                f.write(report_text + "\n")
            console.print(f"[dim]Report saved to {report_path}[/dim]")
        except Exception as e:
            console.print(f"[yellow]Could not save report: {e}[/yellow]")
