"""Full initialization sequence: drop/recreate all DBs and seed with Faker data."""

import os
import random
import string
from datetime import datetime, date

from faker import Faker
from rich.console import Console
from rich.table import Table

from config import (
    DB_DIR,
    INIT_CUSTOMERS, INIT_EMPLOYEES, INIT_CARS,
    INIT_BD_STAFF_MIN, INIT_BD_STAFF_MAX,
    INIT_SALES_STAFF_MIN, INIT_SALES_STAFF_MAX,
    INIT_FINANCE_STAFF_MIN, INIT_FINANCE_STAFF_MAX,
    INIT_INVENTORY_MIN, INIT_INVENTORY_MAX,
    NEW_CAR_PRICE_MIN, NEW_CAR_PRICE_MAX,
    USED_CAR_PRICE_MIN, USED_CAR_PRICE_MAX,
    NEW_CAR_YEARS, USED_CAR_YEARS,
    EMPLOYEE_SALARY_MIN, EMPLOYEE_SALARY_MAX,
    DEPT_BD, DEPT_SALES, DEPT_FINANCE,
    CAR_AVAILABLE, CAR_USED,
    EMP_AVAILABLE, EMP_USED,
    CUST_AVAILABLE,
    DMS_AVAILABLE,
    ERP_SAVINGS_MIN, ERP_SAVINGS_MAX,
    ERP_DEBT_MIN, ERP_DEBT_MAX,
)
from database.session import engine_for, session_for
from models.sim_models import SimBase, SimCustomer, SimEmployee, SimCar, SimResult, EventLog
from models.company_models import (
    CompanyBase, LMSLead, CRMRecord, DMSCar,
    ERPEmployee, ERPTransaction, ERPBalance, LSSLoan, EMSEmployee, EMSCalendar,
)
from data.cars_data import MAKES_MODELS, get_all_combinations
from simulation.state import write_state

console = Console()

# ── DB filename constants ─────────────────────────────────────────────────────
SIM_CUSTOMER_DB = "sim_customers.db"
SIM_EMPLOYEE_DB = "sim_employees.db"
SIM_CAR_DB = "cars_available.db"
SIM_RESULT_DB = "sim_results.db"
EVENTS_DB = "events.db"
LMS_DB = "lms.db"
CRM_DB = "crm.db"
DMS_DB = "dms.db"
ERP_DB = "erp.db"
LSS_DB = "lss.db"
EMS_DB = "ems.db"

ALL_SIM_DBS = [SIM_CUSTOMER_DB, SIM_EMPLOYEE_DB, SIM_CAR_DB, SIM_RESULT_DB, EVENTS_DB]
ALL_COMPANY_DBS = [LMS_DB, CRM_DB, DMS_DB, ERP_DB, LSS_DB, EMS_DB]
ALL_DBS = ALL_SIM_DBS + ALL_COMPANY_DBS


def _generate_vin(rng: random.Random) -> str:
    """Generate a plausible 17-character VIN (no real checksum)."""
    wmi = "".join(rng.choices(string.ascii_uppercase.replace("I", "").replace("O", "").replace("Q", ""), k=3))
    vds = "".join(rng.choices(string.ascii_uppercase + string.digits, k=6))
    vis = "".join(rng.choices(string.digits, k=2)) + "".join(rng.choices(string.ascii_uppercase + string.digits, k=6))
    return wmi + vds + vis


def _drop_and_create_all(rng: random.Random) -> None:
    """Drop and recreate all 11 database files."""
    os.makedirs(DB_DIR, exist_ok=True)

    # Remove existing DB files
    for db_name in ALL_DBS:
        path = os.path.join(DB_DIR, db_name)
        if os.path.exists(path):
            os.remove(path)

    # Create simulation DB tables
    sim_tables_map = {
        SIM_CUSTOMER_DB: [SimCustomer.__table__],
        SIM_EMPLOYEE_DB: [SimEmployee.__table__],
        SIM_CAR_DB: [SimCar.__table__],
        SIM_RESULT_DB: [SimResult.__table__],
        EVENTS_DB: [EventLog.__table__],
    }
    for db_name, tables in sim_tables_map.items():
        engine = engine_for(db_name)
        SimBase.metadata.create_all(engine, tables=tables)

    # Create company DB tables
    company_tables_map = {
        LMS_DB: [LMSLead.__table__],
        CRM_DB: [CRMRecord.__table__],
        DMS_DB: [DMSCar.__table__],
        ERP_DB: [ERPEmployee.__table__, ERPTransaction.__table__, ERPBalance.__table__],
        LSS_DB: [LSSLoan.__table__],
        EMS_DB: [EMSEmployee.__table__, EMSCalendar.__table__],
    }
    for db_name, tables in company_tables_map.items():
        engine = engine_for(db_name)
        CompanyBase.metadata.create_all(engine, tables=tables)


def _seed_customers(fake: Faker, rng: random.Random) -> int:
    session = session_for(SIM_CUSTOMER_DB)
    customers = []
    for _ in range(INIT_CUSTOMERS):
        customers.append(SimCustomer(
            name=fake.name(),
            address=fake.street_address(),
            city=fake.city(),
            state=fake.state_abbr(),
            zip=fake.zipcode(),
            phone=fake.phone_number(),
            email=fake.email(),
            status=CUST_AVAILABLE,
        ))
    session.add_all(customers)
    session.commit()
    session.close()
    return len(customers)


def _seed_employees(fake: Faker, rng: random.Random) -> int:
    session = session_for(SIM_EMPLOYEE_DB)
    employees = []
    for _ in range(INIT_EMPLOYEES):
        employees.append(SimEmployee(
            name=fake.name(),
            address=fake.street_address(),
            phone=fake.phone_number(),
            email=fake.email(),
            weekly_salary=round(rng.uniform(EMPLOYEE_SALARY_MIN, EMPLOYEE_SALARY_MAX), 2),
            department=None,
            status=EMP_AVAILABLE,
        ))
    session.add_all(employees)
    session.commit()
    session.close()
    return len(employees)


def _seed_cars(rng: random.Random) -> int:
    session = session_for(SIM_CAR_DB)
    combos = get_all_combinations()
    cars = []
    used_vins: set[str] = set()
    for _ in range(INIT_CARS):
        condition = rng.choice(["new", "used"])
        make, model = rng.choice(combos)
        year = rng.choice(NEW_CAR_YEARS if condition == "new" else USED_CAR_YEARS)
        price_range = (NEW_CAR_PRICE_MIN, NEW_CAR_PRICE_MAX) if condition == "new" else (USED_CAR_PRICE_MIN, USED_CAR_PRICE_MAX)
        # Generate unique VIN
        vin = _generate_vin(rng)
        while vin in used_vins:
            vin = _generate_vin(rng)
        used_vins.add(vin)
        cars.append(SimCar(
            make=make,
            model=model,
            year=year,
            vin=vin,
            condition=condition,
            min_price=round(rng.uniform(*price_range), 2),
            status=CAR_AVAILABLE,
        ))
    session.add_all(cars)
    session.commit()
    session.close()
    return len(cars)


def _setup_staff(rng: random.Random) -> dict:
    """Pick employees for BD/Sales/Finance, insert into ERP/EMS."""
    sim_session = session_for(SIM_EMPLOYEE_DB)
    erp_session = session_for(ERP_DB)
    ems_session = session_for(EMS_DB)

    available_emps = sim_session.query(SimEmployee).filter_by(status=EMP_AVAILABLE).all()
    rng.shuffle(available_emps)

    counts = {}

    def assign_dept(dept: str, min_count: int, max_count: int, add_to_ems: bool = False) -> list:
        n = rng.randint(min_count, max_count)
        chosen = available_emps[:n]
        del available_emps[:n]
        for emp in chosen:
            emp.department = dept
            emp.status = EMP_USED
            sim_session.merge(emp)
            erp_emp = ERPEmployee(name=emp.name, weekly_salary=emp.weekly_salary, department=dept)
            erp_session.add(erp_emp)
            if add_to_ems:
                ems_emp = EMSEmployee(name=emp.name, department=dept, current_customers=0, last_assignment=None)
                ems_session.add(ems_emp)
        return chosen

    bd_staff = assign_dept(DEPT_BD, INIT_BD_STAFF_MIN, INIT_BD_STAFF_MAX)
    sales_staff = assign_dept(DEPT_SALES, INIT_SALES_STAFF_MIN, INIT_SALES_STAFF_MAX, add_to_ems=True)
    finance_staff = assign_dept(DEPT_FINANCE, INIT_FINANCE_STAFF_MIN, INIT_FINANCE_STAFF_MAX)

    sim_session.commit()
    erp_session.commit()
    ems_session.commit()
    sim_session.close()
    erp_session.close()
    ems_session.close()

    counts = {
        "bd": len(bd_staff),
        "sales": len(sales_staff),
        "finance": len(finance_staff),
    }
    return counts


def _setup_inventory(rng: random.Random) -> int:
    """Pick N cars from sim_cars and insert into DMS."""
    sim_session = session_for(SIM_CAR_DB)
    dms_session = session_for(DMS_DB)

    available_cars = sim_session.query(SimCar).filter_by(status=CAR_AVAILABLE).all()
    n = rng.randint(INIT_INVENTORY_MIN, INIT_INVENTORY_MAX)
    chosen = rng.sample(available_cars, min(n, len(available_cars)))

    for car in chosen:
        car.status = CAR_USED
        sim_session.merge(car)
        dms_car = DMSCar(
            make=car.make,
            model=car.model,
            year=car.year,
            vin=car.vin,
            condition=car.condition,
            min_price=car.min_price,
            status=DMS_AVAILABLE,
        )
        dms_session.add(dms_car)

    sim_session.commit()
    dms_session.commit()
    sim_session.close()
    dms_session.close()
    return len(chosen)


def _seed_erp_balance(rng: random.Random) -> tuple[float, float]:
    """Insert the single-row opening balance into erp_balance."""
    cash = round(rng.uniform(ERP_SAVINGS_MIN, ERP_SAVINGS_MAX), 2)
    debt = round(rng.uniform(ERP_DEBT_MIN,    ERP_DEBT_MAX),    2)
    session = session_for(ERP_DB)
    session.add(ERPBalance(cash=cash, debt=debt))
    session.commit()
    session.close()
    return cash, debt


def run_seeder(rng: random.Random, start_date: date, end_date: date, args=None) -> None:
    """Full initialization sequence."""
    fake = Faker()
    Faker.seed(rng.randint(0, 2**31))

    console.print("\n[bold cyan]Initializing Main Street Motors simulation...[/bold cyan]")

    _drop_and_create_all(rng)

    n_customers = _seed_customers(fake, rng)
    n_employees = _seed_employees(fake, rng)
    n_cars = _seed_cars(rng)
    staff_counts = _setup_staff(rng)
    n_inventory = _setup_inventory(rng)
    opening_cash, opening_debt = _seed_erp_balance(rng)

    # Write initial state file
    write_state(
        status="ready",
        current_date=start_date,
        start_date=start_date,
        end_date=end_date,
        day_number=0,
        total_days=(end_date - start_date).days,
        last_completed_worker=None,
        workers_enabled=[],
        workers_disabled=[],
    )

    # Summary table
    table = Table(title="Initialization Summary", show_header=True, header_style="bold magenta")
    table.add_column("Component", style="cyan")
    table.add_column("Count", justify="right", style="green")
    table.add_row("Customers generated", str(n_customers))
    table.add_row("Employees generated", str(n_employees))
    table.add_row("Cars generated", str(n_cars))
    table.add_row("BD staff assigned", str(staff_counts["bd"]))
    table.add_row("Sales staff assigned", str(staff_counts["sales"]))
    table.add_row("Finance staff assigned", str(staff_counts["finance"]))
    table.add_row("Initial DMS inventory", str(n_inventory))
    table.add_row("Opening cash",  f"${opening_cash:,.2f}")
    table.add_row("Opening debt",  f"${opening_debt:,.2f}")
    table.add_row("Databases created", str(len(ALL_DBS)))
    console.print(table)
    console.print("[bold green]Initialization complete.[/bold green]\n")
