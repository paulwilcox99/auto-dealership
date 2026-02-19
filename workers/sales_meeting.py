"""sales_meeting worker — processes scheduled CRM appointments."""

import random
from datetime import date

from simulation.console import sim_console as console

from config import (
    SALES_NO_SHOW_RATE, SALES_IN_NEGOTIATION_RATE, SALES_NO_SALE_RATE,
    CRM_SCHEDULED, CRM_NO_SHOW, CRM_MET, CRM_WAITING, CRM_IN_NEGOTIATION, CRM_NO_SALE,
    DMS_AVAILABLE, DMS_IN_NEGOTIATION,
)
from database.session import session_for
from models.company_models import CRMRecord, DMSCar
from simulation.llm import create_note, reset_worker_call_count
from workers.base import BaseWorker

CRM_DB = "crm.db"
DMS_DB = "dms.db"


class SalesMeetingWorker(BaseWorker):
    name = "sales_meeting"

    def run(self, sim_date: date, rng: random.Random) -> dict:
        reset_worker_call_count()
        crm_session = session_for(CRM_DB)
        dms_session = session_for(DMS_DB)

        scheduled = crm_session.query(CRMRecord).filter_by(status=CRM_SCHEDULED).all()

        for record in scheduled:
            old_status = record.status

            if rng.random() < SALES_NO_SHOW_RATE:
                record.status = CRM_NO_SHOW
                note = create_note(record.customer_name, record.get_notes(), "customer did not show for scheduled appointment", sim_date)
                record.add_note(sim_date.isoformat(), note)
                crm_session.merge(record)
                console.print(
                    f"[dim]{sim_date}[/dim] [cyan]sales_meeting[/cyan] ─ "
                    f"CRM #{record.id} ({record.customer_name}): {old_status} → {record.status}"
                )
                continue

            # Customer showed up
            record.status = CRM_MET
            record.meeting_date = sim_date

            # Assign a random available car
            available_cars = dms_session.query(DMSCar).filter_by(status=DMS_AVAILABLE).all()
            if available_cars:
                car = rng.choice(available_cars)
                record.car_make = car.make
                record.car_model = car.model
                record.car_year = car.year
                record.car_vin = car.vin
                record.car_condition = car.condition

                if rng.random() < SALES_IN_NEGOTIATION_RATE:
                    record.status = CRM_IN_NEGOTIATION
                    car.status = DMS_IN_NEGOTIATION
                    dms_session.merge(car)
                    note = create_note(
                        record.customer_name, record.get_notes(),
                        f"customer interested in {car.year} {car.make} {car.model} — entered negotiation",
                        sim_date,
                    )
                    record.add_note(sim_date.isoformat(), note)

                    if rng.random() < SALES_NO_SALE_RATE:
                        record.status = CRM_NO_SALE
                        car.status = DMS_AVAILABLE
                        dms_session.merge(car)
                        note2 = create_note(record.customer_name, record.get_notes(), "negotiations fell through — no sale today", sim_date)
                        record.add_note(sim_date.isoformat(), note2)
                else:
                    note = create_note(
                        record.customer_name, record.get_notes(),
                        f"customer met with salesperson — looked at {car.year} {car.make} {car.model} but did not enter negotiation",
                        sim_date,
                    )
                    record.add_note(sim_date.isoformat(), note)
                    record.status = CRM_WAITING
            else:
                note = create_note(record.customer_name, record.get_notes(), "customer met with salesperson — no suitable inventory available", sim_date)
                record.add_note(sim_date.isoformat(), note)
                record.status = CRM_WAITING

            crm_session.merge(record)
            console.print(
                f"[dim]{sim_date}[/dim] [cyan]sales_meeting[/cyan] ─ "
                f"CRM #{record.id} ({record.customer_name}): {old_status} → {record.status}"
                + (f" [{record.car_year} {record.car_make} {record.car_model}]" if record.car_make else "")
            )

        crm_session.commit()
        dms_session.commit()
        crm_session.close()
        dms_session.close()
        return {}
