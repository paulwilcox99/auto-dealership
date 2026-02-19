"""new_cars worker — adds fresh inventory to DMS from sim_cars pool."""

import random
from datetime import date

from simulation.console import sim_console as console

from decimal import Decimal

from config import (
    NEW_CARS_BATCH_MIN, NEW_CARS_BATCH_MAX,
    CAR_AVAILABLE, CAR_USED, DMS_AVAILABLE, ERP_DEBIT,
)
from database.session import session_for
from models.sim_models import SimCar
from models.company_models import DMSCar, ERPTransaction
from workers.base import BaseWorker

SIM_CAR_DB = "sim_cars.db"
DMS_DB = "dms.db"
ERP_DB = "erp.db"


class NewCarsWorker(BaseWorker):
    name = "new_cars"

    def run(self, sim_date: date, rng: random.Random) -> dict:
        sim_session = session_for(SIM_CAR_DB)
        dms_session = session_for(DMS_DB)
        erp_session = session_for(ERP_DB)

        available = sim_session.query(SimCar).filter_by(status=CAR_AVAILABLE).all()
        n = min(rng.randint(NEW_CARS_BATCH_MIN, NEW_CARS_BATCH_MAX), len(available))

        if n == 0:
            sim_session.close()
            dms_session.close()
            erp_session.close()
            console.print(f"[dim]{sim_date}[/dim] [cyan]new_cars[/cyan] ─ No cars available in sim pool.")
            return {}

        total_cost = Decimal("0")
        chosen = rng.sample(available, n)
        for car in chosen:
            car.status = CAR_USED
            sim_session.merge(car)
            dms_car = DMSCar(
                make=car.make,
                model=car.model,
                year=car.year,
                vin=car.vin,
                condition=car.condition,
                min_price=car.min_price,
                status=DMS_AVAILABLE,
            )
            dms_session.add(dms_car)

            cost = car.min_price or Decimal("0")
            erp_session.add(ERPTransaction(
                transaction_type=ERP_DEBIT,
                amount=cost,
                payee_payer="Vehicle Acquisition",
                description=f"Inventory purchase — {car.year} {car.make} {car.model} VIN:{car.vin}",
                transaction_date=sim_date,
            ))
            total_cost += Decimal(str(cost))

            console.print(
                f"[dim]{sim_date}[/dim] [cyan]new_cars[/cyan] ─ "
                f"Added {car.year} {car.make} {car.model} ({car.condition}) VIN:{car.vin} "
                f"cost ${float(cost):,.0f}"
            )

        sim_session.commit()
        dms_session.commit()
        erp_session.commit()
        sim_session.close()
        dms_session.close()
        erp_session.close()
        return {"total_car_costs": float(total_cost), "cars_acquired": n}
