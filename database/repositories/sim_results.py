"""Repository for sim_results.db."""

from database.repositories._base_sqla import SQLARepository
from models.sim_models import SimResult


class SimResultRepository(SQLARepository):
    model_class = SimResult
