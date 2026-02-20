"""All constants, probability weights, and schedules for the simulation."""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Database ──────────────────────────────────────────────────────────────────
DB_DIR = os.getenv("DB_DIR", "./data")
DB_DRIVER = os.getenv("DB_DRIVER", "sqlite")

# ── OpenAI ────────────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = "gpt-4o-mini"
LLM_MAX_CALLS_PER_WORKER = 10

# ── Initialization counts ─────────────────────────────────────────────────────
INIT_CUSTOMERS = 1000
INIT_EMPLOYEES = 1000
INIT_CARS = 1000

INIT_BD_STAFF_MIN = 5
INIT_BD_STAFF_MAX = 10
INIT_SALES_STAFF_MIN = 5
INIT_SALES_STAFF_MAX = 10
INIT_FINANCE_STAFF_MIN = 5
INIT_FINANCE_STAFF_MAX = 10

INIT_INVENTORY_MIN = 50
INIT_INVENTORY_MAX = 100

# ── Car pricing ───────────────────────────────────────────────────────────────
NEW_CAR_PRICE_MIN = 25_000
NEW_CAR_PRICE_MAX = 100_000
USED_CAR_PRICE_MIN = 10_000
USED_CAR_PRICE_MAX = 50_000
NEW_CAR_YEARS = list(range(2022, 2026))
USED_CAR_YEARS = list(range(2010, 2023))

# ── Worker scheduling ─────────────────────────────────────────────────────────
LEAD_CREATION_INTERVAL = 5       # every N days, starting day 0
SALES_FOLLOWUP_INTERVAL = 3     # every N days from start
NEW_CARS_INTERVAL = 5           # every N days from start
LEAD_CREATION_BATCH_MIN = 10
LEAD_CREATION_BATCH_MAX = 30

# ── Lead processing probabilities ────────────────────────────────────────────
LEAD_CONTACT_RATE = 0.70          # probability of reaching a new lead
LEAD_INTEREST_RATE = 0.50         # probability of interested after contacted
LEAD_SCHEDULE_RATE = 0.40         # probability of scheduling from interested
LEAD_NO_INTEREST_RATE = 0.30      # probability of not_interested after contacted

# ── Walk-in probabilities ────────────────────────────────────────────────────
WALK_IN_MIN = 1
WALK_IN_MAX = 5

# ── Sales meeting probabilities ───────────────────────────────────────────────
SALES_NO_SHOW_RATE = 0.20
SALES_IN_NEGOTIATION_RATE = 0.60
SALES_NO_SALE_RATE = 0.40        # of those who reach in_negotiation

# ── Finance probabilities ─────────────────────────────────────────────────────
FINANCE_LOAN_RATE = 0.65         # probability of loan vs cash deal
LOAN_INTEREST_RATE_MIN = 0.04
LOAN_INTEREST_RATE_MAX = 0.12
LOAN_TERM_MONTHS_OPTIONS = [24, 36, 48, 60, 72]
DOWN_PAYMENT_RATE_MIN = 0.10
DOWN_PAYMENT_RATE_MAX = 0.30

# ── Follow-up probabilities ───────────────────────────────────────────────────
FOLLOWUP_RESCHEDULE_RATE = 0.30  # no_show → reschedule
FOLLOWUP_DROP_RATE = 0.20        # met/no_sale → drop (not_interested)

# ── New car inventory ─────────────────────────────────────────────────────────
NEW_CARS_BATCH_MIN = 5
NEW_CARS_BATCH_MAX = 15

# ── Starting balance sheet ────────────────────────────────────────────────────
ERP_SAVINGS_MIN = 1_000_000
ERP_SAVINGS_MAX = 20_000_000
ERP_DEBT_MIN    = 100_000
ERP_DEBT_MAX    = 5_000_000

# ── Salary / payday ───────────────────────────────────────────────────────────
EMPLOYEE_SALARY_MIN = 2_000
EMPLOYEE_SALARY_MAX = 20_000

# ── Status enums (strings used across all workers) ───────────────────────────

# sim_customers.status
CUST_AVAILABLE = "available"
CUST_WALK_IN = "walk-in"
CUST_LEAD = "lead"
CUST_SOLD = "sold"

# sim_employees.status
EMP_AVAILABLE = "available"
EMP_USED = "used"

# sim_cars.status
CAR_AVAILABLE = "available"
CAR_USED = "used"

# sim_employees.department
DEPT_BD = "BD"
DEPT_SALES = "sales"
DEPT_FINANCE = "finance"
DEPT_ACCESSORIES = "accessories"
DEPT_SERVICE = "service"

# lms.status
LMS_NEW = "new"
LMS_CONTACTED = "contacted"
LMS_INTERESTED = "interested"
LMS_NOT_INTERESTED = "not_interested"
LMS_SCHEDULE = "schedule"
LMS_SCHEDULED = "scheduled"
LMS_NO_SHOW = "no_show"
LMS_MET = "met"

# crm.status
CRM_SCHEDULED = "scheduled"
CRM_NO_SHOW = "no_show"
CRM_MET = "met"
CRM_WAITING = "waiting"
CRM_IN_NEGOTIATION = "in_negotiation"
CRM_NO_SALE = "no_sale"
CRM_SOLD = "sold"

# dms.status
DMS_AVAILABLE = "available"
DMS_IN_NEGOTIATION = "in_negotiation"
DMS_SOLD = "sold"

# erp transaction types
ERP_CREDIT = "credit"
ERP_DEBIT = "debit"
