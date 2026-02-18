"""Repository for crm.db (Customer Relationship Manager)."""

from database.repositories._base_sqla import SQLARepository
from models.company_models import CRMRecord


class CRMRepository(SQLARepository):
    model_class = CRMRecord
