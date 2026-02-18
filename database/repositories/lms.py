"""Repository for lms.db (Lead Management System)."""

from database.repositories._base_sqla import SQLARepository
from models.company_models import LMSLead


class LMSRepository(SQLARepository):
    model_class = LMSLead
