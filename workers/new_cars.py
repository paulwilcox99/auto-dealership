"""new_cars worker — adds fresh inventory to DMS from sim_cars pool."""

import random
from datetime import date

from rich.console import Console

from config import (
    NEW_CARS_BATCH_MIN, NEW_CARS_BATCH_MAX,
    CAR_AVAILABLE, CAR_USED, DMS_AVAILABLE,
)
from database.session import session_for
from models.sim_models import SimCar
from models.company_models import DMSCar
from workers.base import BaseWorker

console = Console()
SIM_CAR_DB = "sim_cars.db"
DMS_DB = "dms.db"


class NewCarsWorker(BaseWorker):
    name = "new_cars"

    def run(self, sim_date: date, rng: random.Random) -> dict:
        sim_session = session_for(SIM_CAR_DB)
        dms_session = session_for(DMS_DB)

        available = sim_session.query(SimCar).filter_by(status=CAR_AVAILABLE).all()
        n = min(rng.randint(NEW_CARS_BATCH_MIN, NEW_CARS_BATCH_MAX), len(available))

        if n == 0:
            sim_session.close()
            dms_session.close()
            console.print(f"[dim]{sim_date}[/dim] [cyan]new_cars[/cyan] ─ No cars available in sim pool.")
            return {}

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
            console.print(
                f"[dim]{sim_date}[/dim] [cyan]new_cars[/cyan] ─ "
                f"Added {car.year} {car.make} {car.model} ({car.condition}) VIN:{car.vin}"
            )

        sim_session.commit()
        dms_session.commit()
        sim_session.close()
        dms_session.close()
        return {}
