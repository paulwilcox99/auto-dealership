"""lead_creation worker — pulls available customers into LMS as new leads."""

import random
from datetime import date

from rich.console import Console

from config import (
    LEAD_CREATION_BATCH_MIN, LEAD_CREATION_BATCH_MAX,
    CUST_AVAILABLE, CUST_LEAD, LMS_NEW,
)
from database.session import session_for
from models.sim_models import SimCustomer
from models.company_models import LMSLead
from simulation.events import log_event
from workers.base import BaseWorker

console = Console()

SIM_CUSTOMER_DB = "sim_customers.db"
LMS_DB = "lms.db"


class LeadCreationWorker(BaseWorker):
    name = "lead_creation"

    def run(self, sim_date: date, rng: random.Random) -> dict:
        sim_session = session_for(SIM_CUSTOMER_DB)
        lms_session = session_for(LMS_DB)

        available = sim_session.query(SimCustomer).filter_by(status=CUST_AVAILABLE).all()
        n = min(rng.randint(LEAD_CREATION_BATCH_MIN, LEAD_CREATION_BATCH_MAX), len(available))

        if n == 0:
            sim_session.close()
            lms_session.close()
            return {"new_leads": 0}

        chosen = rng.sample(available, n)
        new_leads = []
        for cust in chosen:
            cust.status = CUST_LEAD
            sim_session.merge(cust)
            lead = LMSLead(
                customer_name=cust.name,
                address=cust.address,
                phone=cust.phone,
                email=cust.email,
                notes="[]",
                status=LMS_NEW,
                last_updated=sim_date,
            )
            lms_session.add(lead)
            new_leads.append(cust.name)
            log_event(sim_date, "lead_creation", "create", "lms_lead", None, None, LMS_NEW, description=f"New lead: {cust.name}")
            console.print(
                f"[dim]{sim_date}[/dim] [cyan]lead_creation[/cyan] — "
                f"New lead: {cust.name}"
            )

        sim_session.commit()
        lms_session.commit()
        sim_session.close()
        lms_session.close()

        return {"new_leads": len(new_leads)}
