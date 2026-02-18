"""Repository for lss.db (Loan Service System)."""

from database.repositories._base_sqla import SQLARepository
from models.company_models import LSSLoan


class LSSRepository(SQLARepository):
    model_class = LSSLoan
