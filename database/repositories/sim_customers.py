"""Repository for sim_customers.db."""

from database.repositories._base_sqla import SQLARepository
from models.sim_models import SimCustomer


class SimCustomerRepository(SQLARepository):
    model_class = SimCustomer
