"""Repository for ems.db (Employee Management System)."""

from database.repositories._base_sqla import SQLARepository
from models.company_models import EMSEmployee, EMSCalendar


class EMSEmployeeRepository(SQLARepository):
    model_class = EMSEmployee


class EMSCalendarRepository(SQLARepository):
    model_class = EMSCalendar
