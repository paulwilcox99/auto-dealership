"""walk_ins worker — random customers walk in without an appointment."""

import random
from datetime import date, time as dt_time

from rich.console import Console

from config import (
    WALK_IN_MIN, WALK_IN_MAX,
    CUST_AVAILABLE, CUST_WALK_IN,
    CRM_SCHEDULED,
)
from database.session import session_for
from models.sim_models import SimCustomer
from models.company_models import CRMRecord, EMSEmployee, EMSCalendar
from simulation.llm import create_note, reset_worker_call_count
from workers.base import BaseWorker

console = Console()
SIM_CUSTOMER_DB = "sim_customers.db"
CRM_DB = "crm.db"
EMS_DB = "ems.db"


class WalkInsWorker(BaseWorker):
    name = "walk_ins"

    def run(self, sim_date: date, rng: random.Random) -> dict:
        reset_worker_call_count()
        sim_session = session_for(SIM_CUSTOMER_DB)
        crm_session = session_for(CRM_DB)
        ems_session = session_for(EMS_DB)

        available = sim_session.query(SimCustomer).filter_by(status=CUST_AVAILABLE).all()
        n = min(rng.randint(WALK_IN_MIN, WALK_IN_MAX), len(available))

        if n == 0:
            sim_session.close()
            crm_session.close()
            ems_session.close()
            return {}

        salespeople = ems_session.query(EMSEmployee).filter_by(department="sales").all()
        if not salespeople:
            sim_session.close()
            crm_session.close()
            ems_session.close()
            return {}

        chosen = rng.sample(available, n)
        for cust in chosen:
            cust.status = CUST_WALK_IN
            sim_session.merge(cust)

            sp = min(salespeople, key=lambda e: e.current_customers or 0)
            sp.current_customers = (sp.current_customers or 0) + 1
            ems_session.merge(sp)

            crm = CRMRecord(
                customer_name=cust.name,
                address=cust.address,
                phone=cust.phone,
                email=cust.email,
                salesperson_name=sp.name,
                meeting_date=sim_date,
                notes="[]",
                status=CRM_SCHEDULED,
            )
            note = create_note(cust.name, [], "customer walked in off the street — no appointment", sim_date)
            crm.add_note(sim_date.isoformat(), note)
            crm_session.add(crm)

            console.print(
                f"[dim]{sim_date}[/dim] [cyan]walk_ins[/cyan] ─ "
                f"Walk-in: {cust.name} → assigned to {sp.name}"
            )

        sim_session.commit()
        crm_session.commit()
        ems_session.commit()
        sim_session.close()
        crm_session.close()
        ems_session.close()
        return {}
