"""Repository for cars_available.db."""

from database.repositories._base_sqla import SQLARepository
from models.sim_models import SimCar


class SimCarRepository(SQLARepository):
    model_class = SimCar
