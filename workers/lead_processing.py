"""lead_processing worker — BD staff contacts and qualifies LMS leads."""

import random
from datetime import date

from simulation.console import sim_console as console

from config import (
    LEAD_CONTACT_RATE, LEAD_INTEREST_RATE, LEAD_NO_INTEREST_RATE,
    LMS_NEW, LMS_CONTACTED, LMS_INTERESTED, LMS_NOT_INTERESTED,
)
from database.session import session_for
from models.company_models import LMSLead
from simulation.llm import create_note, reset_worker_call_count
from workers.base import BaseWorker

LMS_DB = "lms.db"


class LeadProcessingWorker(BaseWorker):
    name = "lead_processing"

    def run(self, sim_date: date, rng: random.Random) -> dict:
        reset_worker_call_count()
        session = session_for(LMS_DB)
        leads = session.query(LMSLead).filter(
            LMSLead.status.in_([LMS_NEW, LMS_CONTACTED])
        ).all()

        processed = 0
        for lead in leads:
            old_status = lead.status

            if lead.status == LMS_NEW:
                if rng.random() < LEAD_CONTACT_RATE:
                    lead.status = LMS_CONTACTED
                    note = create_note(lead.customer_name, lead.get_notes(), "BD rep called lead for the first time", sim_date)
                else:
                    note = create_note(lead.customer_name, lead.get_notes(), "BD rep attempted to call — no answer", sim_date)

            elif lead.status == LMS_CONTACTED:
                if rng.random() < LEAD_INTEREST_RATE:
                    lead.status = LMS_INTERESTED
                    note = create_note(lead.customer_name, lead.get_notes(), "customer expressed interest in visiting dealership", sim_date)
                elif rng.random() < LEAD_NO_INTEREST_RATE:
                    lead.status = LMS_NOT_INTERESTED
                    note = create_note(lead.customer_name, lead.get_notes(), "customer declined — not interested at this time", sim_date)
                else:
                    note = create_note(lead.customer_name, lead.get_notes(), "follow-up call — customer still undecided", sim_date)

            else:
                continue

            lead.add_note(sim_date.isoformat(), note)
            lead.last_updated = sim_date
            session.merge(lead)
            processed += 1

            console.print(
                f"[dim]{sim_date}[/dim] [cyan]lead_processing[/cyan] ─ "
                f"Lead #{lead.id} ({lead.customer_name}): "
                f"{old_status} → {lead.status} [note added]"
            )

        session.commit()
        session.close()
        return {"leads_processed": processed}
