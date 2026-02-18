"""Worker registry — ordered list of all workers and dispatch helpers."""

from workers.lead_creation import LeadCreationWorker
from workers.lead_processing import LeadProcessingWorker
from workers.schedule_lead import ScheduleLeadWorker
from workers.walk_ins import WalkInsWorker
from workers.sales_meeting import SalesMeetingWorker
from workers.sales_followup import SalesFollowupWorker
from workers.new_cars import NewCarsWorker
from workers.finance_sales import FinanceSalesWorker
from workers.finance_payments import FinancePaymentsWorker
from workers.payday import PaydayWorker

# Canonical ordered list of worker names
WORKER_NAMES: list[str] = [
    "lead_creation",
    "lead_processing",
    "schedule_lead",
    "walk_ins",
    "sales_meeting",
    "sales_followup",
    "new_cars",
    "finance_sales",
    "finance_payments",
    "payday",
]

# Map name → class
WORKER_REGISTRY: dict = {
    "lead_creation": LeadCreationWorker,
    "lead_processing": LeadProcessingWorker,
    "schedule_lead": ScheduleLeadWorker,
    "walk_ins": WalkInsWorker,
    "sales_meeting": SalesMeetingWorker,
    "sales_followup": SalesFollowupWorker,
    "new_cars": NewCarsWorker,
    "finance_sales": FinanceSalesWorker,
    "finance_payments": FinancePaymentsWorker,
    "payday": PaydayWorker,
}


def get_worker_instances(enabled_workers: list[str]) -> list:
    """Return instantiated worker objects in registry order, filtered to enabled_workers."""
    instances = []
    for name in WORKER_NAMES:
        if name in enabled_workers:
            cls = WORKER_REGISTRY[name]
            instances.append(cls())
    return instances
