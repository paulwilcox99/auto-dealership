"""sales_followup worker — follows up on no-shows and stalled CRM records."""

import random
from datetime import date, timedelta

from simulation.console import sim_console as console

from config import (
    FOLLOWUP_RESCHEDULE_RATE, FOLLOWUP_DROP_RATE,
    CRM_NO_SHOW, CRM_WAITING, CRM_NO_SALE, CRM_SCHEDULED,
    LMS_SCHEDULED,
)
from database.session import session_for
from models.company_models import CRMRecord, LMSLead
from simulation.llm import create_note, reset_worker_call_count
from workers.base import BaseWorker

CRM_DB = "crm.db"
LMS_DB = "lms.db"
EMS_DB = "ems.db"


class SalesFollowupWorker(BaseWorker):
    name = "sales_followup"

    def run(self, sim_date: date, rng: random.Random) -> dict:
        reset_worker_call_count()
        crm_session = session_for(CRM_DB)
        lms_session = session_for(LMS_DB)

        # ── CRM no-shows: try to reschedule ──────────────────────────────────
        no_shows = crm_session.query(CRMRecord).filter_by(status=CRM_NO_SHOW).all()
        for record in no_shows:
            if rng.random() < FOLLOWUP_RESCHEDULE_RATE:
                record.status = CRM_SCHEDULED
                note = create_note(record.customer_name, record.get_notes(), "rescheduled appointment after no-show", sim_date)
                record.add_note(sim_date.isoformat(), note)
                crm_session.merge(record)
                console.print(
                    f"[dim]{sim_date}[/dim] [cyan]sales_followup[/cyan] ─ "
                    f"CRM #{record.id} ({record.customer_name}): no_show → scheduled [rescheduled]"
                )

        # ── CRM waiting/no-sale: occasional drop ─────────────────────────────
        stalled = crm_session.query(CRMRecord).filter(
            CRMRecord.status.in_([CRM_WAITING, CRM_NO_SALE])
        ).all()
        for record in stalled:
            if rng.random() < FOLLOWUP_DROP_RATE:
                old = record.status
                record.status = CRM_NO_SALE
                note = create_note(record.customer_name, record.get_notes(), "customer contact lost — closing record", sim_date)
                record.add_note(sim_date.isoformat(), note)
                crm_session.merge(record)
                console.print(
                    f"[dim]{sim_date}[/dim] [cyan]sales_followup[/cyan] ─ "
                    f"CRM #{record.id} ({record.customer_name}): {old} → no_sale [dropped]"
                )
            else:
                note = create_note(record.customer_name, record.get_notes(), "follow-up call — customer still considering", sim_date)
                record.add_note(sim_date.isoformat(), note)
                crm_session.merge(record)

        crm_session.commit()
        lms_session.commit()
        crm_session.close()
        lms_session.close()
        return {}
