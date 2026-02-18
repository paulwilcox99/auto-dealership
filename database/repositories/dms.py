"""Repository for dms.db (Dealer Management System)."""

from database.repositories._base_sqla import SQLARepository
from models.company_models import DMSCar


class DMSRepository(SQLARepository):
    model_class = DMSCar
