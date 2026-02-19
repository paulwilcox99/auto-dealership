"""payday worker — pays all employees every Friday."""

import random
from datetime import date
from decimal import Decimal

from simulation.console import sim_console as console

from config import ERP_DEBIT
from database.session import session_for
from models.company_models import ERPEmployee, ERPTransaction
from simulation.events import log_event
from workers.base import BaseWorker

ERP_DB = "erp.db"


class PaydayWorker(BaseWorker):
    name = "payday"

    def run(self, sim_date: date, rng: random.Random) -> dict:
        erp_session = session_for(ERP_DB)

        employees = erp_session.query(ERPEmployee).all()
        total_payroll = Decimal("0")

        for emp in employees:
            salary = emp.weekly_salary or Decimal("0")
            txn = ERPTransaction(
                transaction_type=ERP_DEBIT,
                amount=salary,
                payee_payer=emp.name,
                description=f"Weekly salary — {emp.department or 'unassigned'}",
                transaction_date=sim_date,
            )
            erp_session.add(txn)
            total_payroll += salary

        erp_session.commit()
        erp_session.close()

        log_event(sim_date, "payday", "payroll", description=f"Paid {len(employees)} employees ${float(total_payroll):,.2f}", amount=float(total_payroll))
        console.print(
            f"[dim]{sim_date}[/dim] [cyan]payday[/cyan] ─ "
            f"Paid {len(employees)} employees — total ${float(total_payroll):,.2f}"
        )
        return {
            "total_salaries": float(total_payroll),
            "total_employees": len(employees),
        }
