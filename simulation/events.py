"""Utility for appending rows to the append-only events.db event log."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from database.session import session_for
from models.sim_models import EventLog

EVENTS_DB = "events.db"


def log_event(
    sim_date: date,
    worker_name: str,
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    old_status: Optional[str] = None,
    new_status: Optional[str] = None,
    amount: Optional[float] = None,
    description: Optional[str] = None,
) -> None:
    """Append one row to events.db."""
    try:
        session = session_for(EVENTS_DB)
        event = EventLog(
            sim_date=sim_date,
            sim_timestamp=datetime.utcnow(),
            worker_name=worker_name,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_status=old_status,
            new_status=new_status,
            amount=Decimal(str(amount)) if amount is not None else None,
            description=description,
        )
        session.add(event)
        session.commit()
        session.close()
    except Exception:
        pass  # Event log failures must never crash the simulation
