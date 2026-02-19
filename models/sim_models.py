"""SQLAlchemy ORM models for the 4 simulation databases."""

from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime
from sqlalchemy.orm import DeclarativeBase


class SimBase(DeclarativeBase):
    pass


# ── sim_customers.db ──────────────────────────────────────────────────────────

class SimCustomer(SimBase):
    __tablename__ = "sim_customers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    address = Column(String)
    city = Column(String)
    state = Column(String)
    zip = Column(String)
    phone = Column(String)
    email = Column(String)
    # available | walk-in | lead | sold
    status = Column(String, nullable=False, default="available")


# ── sim_employees.db ──────────────────────────────────────────────────────────

class SimEmployee(SimBase):
    __tablename__ = "sim_employees"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    address = Column(String)
    phone = Column(String)
    email = Column(String)
    weekly_salary = Column(Numeric(10, 2))
    # BD | sales | finance | accessories | service | NULL
    department = Column(String, nullable=True)
    # available | used
    status = Column(String, nullable=False, default="available")


# ── sim_cars.db ───────────────────────────────────────────────────────────────

class SimCar(SimBase):
    __tablename__ = "sim_cars"

    id = Column(Integer, primary_key=True, autoincrement=True)
    make = Column(String, nullable=False)
    model = Column(String, nullable=False)
    year = Column(Integer, nullable=False)
    vin = Column(String, nullable=False, unique=True)
    # new | used
    condition = Column(String, nullable=False)
    min_price = Column(Numeric(10, 2), nullable=False)
    # available | used
    status = Column(String, nullable=False, default="available")


# ── sim_results.db ────────────────────────────────────────────────────────────

class SimResult(SimBase):
    __tablename__ = "sim_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sim_date = Column(Date, nullable=False)
    cars_sold = Column(Integer, default=0)
    cars_acquired = Column(Integer, default=0)
    new_leads = Column(Integer, default=0)
    leads_processed = Column(Integer, default=0)
    cash_deals = Column(Integer, default=0)
    loans = Column(Integer, default=0)
    total_employees = Column(Integer, default=0)
    total_revenue = Column(Numeric(12, 2), default=0)
    total_car_costs = Column(Numeric(12, 2), default=0)
    total_salaries = Column(Numeric(12, 2), default=0)


# ── events.db ─────────────────────────────────────────────────────────────────

class EventLog(SimBase):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sim_date = Column(Date, nullable=False)
    sim_timestamp = Column(DateTime, nullable=False)
    worker_name = Column(String, nullable=False)
    action = Column(String, nullable=False)
    entity_type = Column(String)
    entity_id = Column(Integer)
    old_status = Column(String)
    new_status = Column(String)
    amount = Column(Numeric(12, 2))
    description = Column(String)
