"""Repository for erp.db (Enterprise Resource Planning)."""

from database.repositories._base_sqla import SQLARepository
from models.company_models import ERPEmployee, ERPTransaction, ERPBalance


class ERPEmployeeRepository(SQLARepository):
    model_class = ERPEmployee


class ERPTransactionRepository(SQLARepository):
    model_class = ERPTransaction


class ERPBalanceRepository(SQLARepository):
    model_class = ERPBalance
