"""SQLAlchemy ORM models for the 6 company databases."""

import json
from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, ForeignKey, Time
from sqlalchemy.orm import DeclarativeBase


class CompanyBase(DeclarativeBase):
    pass


# ── lms.db ────────────────────────────────────────────────────────────────────

class LMSLead(CompanyBase):
    __tablename__ = "lms_leads"

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_name = Column(String, nullable=False)
    address = Column(String)
    phone = Column(String)
    email = Column(String)
    notes = Column(String, default="[]")   # JSON string: [{date, text}, ...]
    # new | contacted | interested | not_interested | schedule | scheduled | no_show | met
    status = Column(String, nullable=False, default="new")
    last_updated = Column(Date)

    def get_notes(self) -> list:
        try:
            return json.loads(self.notes or "[]")
        except (json.JSONDecodeError, TypeError):
            return []

    def add_note(self, date_str: str, text: str) -> None:
        notes = self.get_notes()
        notes.append({"date": date_str, "text": text})
        self.notes = json.dumps(notes)


# ── crm.db ────────────────────────────────────────────────────────────────────

class CRMRecord(CompanyBase):
    __tablename__ = "crm_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_name = Column(String, nullable=False)
    address = Column(String)
    phone = Column(String)
    email = Column(String)
    salesperson_name = Column(String)
    meeting_date = Column(Date)
    notes = Column(String, default="[]")   # JSON string
    # scheduled | no_show | met | waiting | in_negotiation | no_sale | sold
    status = Column(String, nullable=False, default="scheduled")
    car_make = Column(String)
    car_model = Column(String)
    car_year = Column(Integer)
    car_vin = Column(String)
    car_condition = Column(String)
    sale_price = Column(Numeric(10, 2))

    def get_notes(self) -> list:
        try:
            return json.loads(self.notes or "[]")
        except (json.JSONDecodeError, TypeError):
            return []

    def add_note(self, date_str: str, text: str) -> None:
        notes = self.get_notes()
        notes.append({"date": date_str, "text": text})
        self.notes = json.dumps(notes)


# ── dms.db ────────────────────────────────────────────────────────────────────

class DMSCar(CompanyBase):
    __tablename__ = "dms_cars"

    id = Column(Integer, primary_key=True, autoincrement=True)
    make = Column(String, nullable=False)
    model = Column(String, nullable=False)
    year = Column(Integer, nullable=False)
    vin = Column(String, nullable=False, unique=True)
    condition = Column(String, nullable=False)
    min_price = Column(Numeric(10, 2))
    # available | in_negotiation | sold
    status = Column(String, nullable=False, default="available")
    sale_date = Column(Date)
    sale_price = Column(Numeric(10, 2))
    customer_name = Column(String)
    customer_address = Column(String)
    customer_phone = Column(String)
    customer_email = Column(String)


# ── erp.db ────────────────────────────────────────────────────────────────────

class ERPEmployee(CompanyBase):
    __tablename__ = "erp_employees"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    weekly_salary = Column(Numeric(10, 2))
    department = Column(String)


class ERPTransaction(CompanyBase):
    __tablename__ = "erp_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # credit | debit
    transaction_type = Column(String, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    payee_payer = Column(String)
    description = Column(String)
    transaction_date = Column(Date, nullable=False)


class ERPBalance(CompanyBase):
    """Single-row table that tracks the dealership's cash position and debt."""
    __tablename__ = "erp_balance"

    id   = Column(Integer, primary_key=True, autoincrement=True)
    cash = Column(Numeric(14, 2), nullable=False, default=0)
    debt = Column(Numeric(14, 2), nullable=False, default=0)


# ── lss.db ────────────────────────────────────────────────────────────────────

class LSSLoan(CompanyBase):
    __tablename__ = "lss_loans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_name = Column(String, nullable=False)
    address = Column(String)
    phone = Column(String)
    email = Column(String)
    start_date = Column(Date)
    payments_left = Column(Integer)
    payment_amount = Column(Numeric(10, 2))
    interest_rate = Column(Numeric(5, 4))
    down_payment = Column(Numeric(10, 2))
    original_price = Column(Numeric(10, 2))


# ── ems.db ────────────────────────────────────────────────────────────────────

class EMSEmployee(CompanyBase):
    __tablename__ = "ems_employees"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    department = Column(String)
    current_customers = Column(Integer, default=0)
    last_assignment = Column(DateTime)


class EMSCalendar(CompanyBase):
    __tablename__ = "ems_calendar"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(Integer, ForeignKey("ems_employees.id"))
    customer_name = Column(String)
    scheduled_date = Column(Date)
    scheduled_time = Column(Time)
