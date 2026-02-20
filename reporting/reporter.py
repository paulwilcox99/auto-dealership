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
from models.company_models import ERPBalance, ERPTransaction

console = Console()
SIM_RESULT_DB = "sim_results.db"


class Reporter:
    """Collects daily stats, writes to sim_results.db, and prints final report."""

    def __init__(self, start_date: date, end_date: date):
        self.start_date = start_date
        self.end_date = end_date
        self.daily_records: List[dict] = []

    def record_day(self, sim_date: date, stats: dict) -> None:
        """Persist a daily snapshot to sim_results.db and update ERP balance."""
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
        self._update_erp_balance(sim_date)

    def _update_erp_balance(self, sim_date: date) -> None:
        """Apply today's net ERP transactions to the running cash balance."""
        try:
            erp_session = session_for("erp.db")
            txns = (
                erp_session.query(ERPTransaction)
                .filter(ERPTransaction.transaction_date == sim_date)
                .all()
            )
            net = Decimal("0")
            for t in txns:
                if t.transaction_type == "credit":
                    net += Decimal(str(t.amount))
                else:
                    net -= Decimal(str(t.amount))

            balance = erp_session.query(ERPBalance).first()
            if balance:
                balance.cash = Decimal(str(balance.cash)) + net
                erp_session.commit()
            erp_session.close()
        except Exception:
            pass

    def print_final_report(self) -> None:
        """Print and save the end-of-simulation summary."""
        if not self.daily_records:
            console.print("[yellow]No data to report.[/yellow]")
            return

        # Aggregate
        total_sold = sum(d.get("cars_sold", 0) for d in self.daily_records)
        total_cash = sum(d.get("cash_deals", 0) for d in self.daily_records)
        total_loans = sum(d.get("loans", 0) for d in self.daily_records)
        total_leads = sum(d.get("new_leads", 0) for d in self.daily_records)
        total_revenue = sum(d.get("total_revenue", 0) for d in self.daily_records)
        total_salaries = sum(d.get("total_salaries", 0) for d in self.daily_records)

        # Read car acquisition totals from ERP so agent purchases are included
        # even when the new_cars worker is disabled.
        total_acquired = 0
        total_car_costs = 0.0
        try:
            from models.company_models import ERPTransaction
            erp_session = session_for("erp.db")
            acquisitions = (
                erp_session.query(ERPTransaction)
                .filter_by(transaction_type="debit", payee_payer="Vehicle Acquisition")
                .all()
            )
            total_acquired = len(acquisitions)
            total_car_costs = sum(float(t.amount) for t in acquisitions)
            erp_session.close()
        except Exception:
            total_acquired = sum(d.get("cars_acquired", 0) for d in self.daily_records)
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

        # Get current balance sheet from ERP and DMS
        current_cash = 0.0
        current_debt = 0.0
        inventory_value = 0.0
        try:
            erp_bal_session = session_for("erp.db")
            balance = erp_bal_session.query(ERPBalance).first()
            if balance:
                current_cash = float(balance.cash)
                current_debt = float(balance.debt)
            erp_bal_session.close()
        except Exception:
            pass
        try:
            from models.company_models import DMSCar as _DMSCar
            dms_inv_session = session_for("dms.db")
            available_cars = dms_inv_session.query(_DMSCar).filter_by(status="available").all()
            inventory_value = sum(float(c.min_price or 0) for c in available_cars)
            dms_inv_session.close()
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
            f"BALANCE SHEET",
            f"  Cash:                   ${current_cash:,.2f}",
            f"  Inventory value:        ${inventory_value:,.2f}",
            f"  Total assets:           ${current_cash + inventory_value:,.2f}",
            f"  Outstanding debt:       ${current_debt:,.2f}",
            f"  Net equity:             ${current_cash + inventory_value - current_debt:,.2f}",
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
