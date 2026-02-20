"""finance_sales worker — converts in_negotiation CRM records to sales."""

import random
from datetime import date
from decimal import Decimal

from simulation.console import sim_console as console

from config import (
    FINANCE_LOAN_RATE,
    LOAN_INTEREST_RATE_MIN, LOAN_INTEREST_RATE_MAX,
    LOAN_TERM_MONTHS_OPTIONS,
    DOWN_PAYMENT_RATE_MIN, DOWN_PAYMENT_RATE_MAX,
    CRM_IN_NEGOTIATION, CRM_SOLD,
    DMS_IN_NEGOTIATION, DMS_SOLD,
    CUST_SOLD,
    ERP_CREDIT,
)
from database.session import session_for
from models.sim_models import SimCustomer
from models.company_models import CRMRecord, DMSCar, ERPTransaction, LSSLoan, LMSLead
from simulation.llm import create_note, reset_worker_call_count
from simulation.events import log_event
from workers.base import BaseWorker

CRM_DB = "crm.db"
DMS_DB = "dms.db"
ERP_DB = "erp.db"
LSS_DB = "lss.db"
LMS_DB = "lms.db"
SIM_CUSTOMER_DB = "sim_customers.db"


class FinanceSalesWorker(BaseWorker):
    name = "finance_sales"

    def run(self, sim_date: date, rng: random.Random) -> dict:
        reset_worker_call_count()
        crm_session = session_for(CRM_DB)
        dms_session = session_for(DMS_DB)
        erp_session = session_for(ERP_DB)
        lss_session = session_for(LSS_DB)
        lms_session = session_for(LMS_DB)
        sim_session = session_for(SIM_CUSTOMER_DB)

        in_neg = crm_session.query(CRMRecord).filter_by(status=CRM_IN_NEGOTIATION).all()

        cars_sold = 0
        cash_deals = 0
        loans = 0
        total_revenue = Decimal("0")

        for record in in_neg:
            # Not every negotiation closes today — ~60% close rate
            if rng.random() > 0.60:
                continue

            car = dms_session.query(DMSCar).filter_by(vin=record.car_vin).first() if record.car_vin else None
            if car is None:
                continue

            # Sale price: min_price + 0–15% margin
            margin = rng.uniform(0, 0.15)
            sale_price = round(float(car.min_price) * (1 + margin), 2)
            record.sale_price = Decimal(str(sale_price))
            record.status = CRM_SOLD

            car.status = DMS_SOLD
            car.sale_date = sim_date
            car.sale_price = Decimal(str(sale_price))
            car.customer_name = record.customer_name
            car.customer_address = record.address
            car.customer_phone = record.phone
            car.customer_email = record.email

            is_loan = rng.random() < FINANCE_LOAN_RATE
            if is_loan:
                loans += 1
                interest_rate = round(rng.uniform(LOAN_INTEREST_RATE_MIN, LOAN_INTEREST_RATE_MAX), 4)
                term_months = rng.choice(LOAN_TERM_MONTHS_OPTIONS)
                down_pct = rng.uniform(DOWN_PAYMENT_RATE_MIN, DOWN_PAYMENT_RATE_MAX)
                down_payment = round(sale_price * down_pct, 2)
                principal = sale_price - down_payment
                monthly_rate = interest_rate / 12
                if monthly_rate > 0:
                    payment = round(
                        principal * monthly_rate / (1 - (1 + monthly_rate) ** (-term_months)),
                        2,
                    )
                else:
                    payment = round(principal / term_months, 2)

                lss_loan = LSSLoan(
                    customer_name=record.customer_name,
                    address=record.address,
                    phone=record.phone,
                    email=record.email,
                    start_date=sim_date,
                    payments_left=term_months,
                    payment_amount=Decimal(str(payment)),
                    interest_rate=Decimal(str(interest_rate)),
                    down_payment=Decimal(str(down_payment)),
                    original_price=Decimal(str(sale_price)),
                )
                lss_session.add(lss_loan)

                erp_amount = down_payment
                deal_type = f"LOAN ${down_payment:,.0f} down"
                note_ctx = f"customer financed {record.car_year} {record.car_make} {record.car_model} at ${sale_price:,.0f} — loan approved"
            else:
                cash_deals += 1
                erp_amount = sale_price
                deal_type = "CASH"
                note_ctx = f"customer paid cash for {record.car_year} {record.car_make} {record.car_model} at ${sale_price:,.0f}"

            # ERP credit transaction — down payment for loans, full price for cash
            erp_txn = ERPTransaction(
                transaction_type=ERP_CREDIT,
                amount=Decimal(str(erp_amount)),
                payee_payer=record.customer_name,
                description=f"Vehicle sale — {record.car_year} {record.car_make} {record.car_model} VIN:{record.car_vin}",
                transaction_date=sim_date,
            )
            erp_session.add(erp_txn)

            note = create_note(record.customer_name, record.get_notes(), note_ctx, sim_date)
            record.add_note(sim_date.isoformat(), note)
            crm_session.merge(record)
            dms_session.merge(car)

            # Update LMS to "met"
            lms_lead = lms_session.query(LMSLead).filter_by(customer_name=record.customer_name).first()
            if lms_lead:
                lms_lead.status = "met"
                lms_session.merge(lms_lead)

            # Update sim_customers to "sold"
            sim_cust = sim_session.query(SimCustomer).filter_by(name=record.customer_name).first()
            if sim_cust:
                sim_cust.status = CUST_SOLD
                sim_session.merge(sim_cust)

            cars_sold += 1
            total_revenue += Decimal(str(erp_amount))

            log_event(
                sim_date, "finance_sales", "sale",
                "crm_record", record.id,
                CRM_IN_NEGOTIATION, CRM_SOLD,
                amount=sale_price,
                description=f"{record.car_year} {record.car_make} {record.car_model} — {deal_type}",
            )
            console.print(
                f"[dim]{sim_date}[/dim] [cyan]finance_sales[/cyan] ─ "
                f"CRM #{record.id} ({record.customer_name}): "
                f"in_negotiation → sold [{deal_type} | sale ${sale_price:,.2f}]"
            )

        crm_session.commit()
        dms_session.commit()
        erp_session.commit()
        lss_session.commit()
        lms_session.commit()
        sim_session.commit()
        crm_session.close()
        dms_session.close()
        erp_session.close()
        lss_session.close()
        lms_session.close()
        sim_session.close()

        return {
            "cars_sold": cars_sold,
            "cash_deals": cash_deals,
            "loans": loans,
            "total_revenue": float(total_revenue),
        }
