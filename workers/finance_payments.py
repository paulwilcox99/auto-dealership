"""finance_payments worker — processes monthly loan payments (runs 1st of each month)."""

import random
from datetime import date
from decimal import Decimal

from rich.console import Console

from config import ERP_CREDIT
from database.session import session_for
from models.company_models import LSSLoan, ERPTransaction
from workers.base import BaseWorker

console = Console()
LSS_DB = "lss.db"
ERP_DB = "erp.db"


class FinancePaymentsWorker(BaseWorker):
    name = "finance_payments"

    def run(self, sim_date: date, rng: random.Random) -> dict:
        lss_session = session_for(LSS_DB)
        erp_session = session_for(ERP_DB)

        active_loans = lss_session.query(LSSLoan).filter(LSSLoan.payments_left > 0).all()

        total_collected = Decimal("0")
        payments_processed = 0

        for loan in active_loans:
            payment = loan.payment_amount or Decimal("0")
            loan.payments_left = max(0, (loan.payments_left or 1) - 1)
            lss_session.merge(loan)

            erp_txn = ERPTransaction(
                transaction_type=ERP_CREDIT,
                amount=payment,
                payee_payer=loan.customer_name,
                description=f"Loan payment — {loan.payments_left} payments remaining",
                transaction_date=sim_date,
            )
            erp_session.add(erp_txn)
            total_collected += payment
            payments_processed += 1

            console.print(
                f"[dim]{sim_date}[/dim] [cyan]finance_payments[/cyan] ─ "
                f"Loan for {loan.customer_name}: payment ${float(payment):,.2f} "
                f"({loan.payments_left} remaining)"
            )

        lss_session.commit()
        erp_session.commit()
        lss_session.close()
        erp_session.close()
        return {"loan_payments": payments_processed, "loan_revenue": float(total_collected)}
