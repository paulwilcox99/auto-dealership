"""Repository for sim_employees.db."""

from database.repositories._base_sqla import SQLARepository
from models.sim_models import SimEmployee


class SimEmployeeRepository(SQLARepository):
    model_class = SimEmployee
