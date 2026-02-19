"""schedule_lead worker — books appointments for interested LMS leads."""

import random
from datetime import date, timedelta, time as dt_time

from simulation.console import sim_console as console

from config import (
    LEAD_SCHEDULE_RATE,
    LMS_INTERESTED, LMS_SCHEDULE, LMS_SCHEDULED,
)
from database.session import session_for
from models.company_models import LMSLead, EMSEmployee, EMSCalendar
from simulation.llm import create_note, reset_worker_call_count
from workers.base import BaseWorker

LMS_DB = "lms.db"
EMS_DB = "ems.db"

APPOINTMENT_HOURS = [9, 10, 11, 13, 14, 15, 16, 17]


class ScheduleLeadWorker(BaseWorker):
    name = "schedule_lead"

    def run(self, sim_date: date, rng: random.Random) -> dict:
        reset_worker_call_count()
        lms_session = session_for(LMS_DB)
        ems_session = session_for(EMS_DB)

        interested = lms_session.query(LMSLead).filter(
            LMSLead.status.in_([LMS_INTERESTED, LMS_SCHEDULE])
        ).all()

        salespeople = ems_session.query(EMSEmployee).filter_by(department="sales").all()
        if not salespeople:
            lms_session.close()
            ems_session.close()
            return {}

        scheduled_count = 0
        for lead in interested:
            if rng.random() > LEAD_SCHEDULE_RATE:
                continue

            old_status = lead.status
            lead.status = LMS_SCHEDULED

            # Pick a salesperson (round-robin by current_customers)
            sp = min(salespeople, key=lambda e: e.current_customers or 0)
            sp.current_customers = (sp.current_customers or 0) + 1
            sp.last_assignment = sim_date

            # Schedule 1–5 business days out
            appt_date = sim_date + timedelta(days=rng.randint(1, 5))
            appt_hour = rng.choice(APPOINTMENT_HOURS)
            appt_time = dt_time(hour=appt_hour, minute=0)

            cal_entry = EMSCalendar(
                employee_id=sp.id,
                customer_name=lead.customer_name,
                scheduled_date=appt_date,
                scheduled_time=appt_time,
            )
            ems_session.add(cal_entry)
            ems_session.merge(sp)

            note = create_note(
                lead.customer_name,
                lead.get_notes(),
                f"appointment scheduled for {appt_date} with salesperson {sp.name}",
                sim_date,
            )
            lead.add_note(sim_date.isoformat(), note)
            lead.last_updated = sim_date
            lms_session.merge(lead)
            scheduled_count += 1

            console.print(
                f"[dim]{sim_date}[/dim] [cyan]schedule_lead[/cyan] ─ "
                f"Lead #{lead.id} ({lead.customer_name}): "
                f"{old_status} → {lead.status} [appt {appt_date} {appt_time:%H:%M}]"
            )

        lms_session.commit()
        ems_session.commit()
        lms_session.close()
        ems_session.close()
        return {}
