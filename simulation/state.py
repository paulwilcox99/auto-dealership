"""Read/write simulation_state.json for external program coordination."""

import json
import os
from datetime import date, datetime
from typing import List, Optional

from config import DB_DIR

STATE_FILE = "simulation_state.json"


def _state_path() -> str:
    return os.path.join(DB_DIR, STATE_FILE)


def write_state(
    status: str,
    current_date: date,
    start_date: date,
    end_date: date,
    day_number: int,
    total_days: int,
    last_completed_worker: Optional[str],
    workers_enabled: List[str],
    workers_disabled: List[str],
) -> None:
    """Write the current simulation state to simulation_state.json."""
    os.makedirs(DB_DIR, exist_ok=True)
    state = {
        "status": status,
        "current_date": current_date.isoformat(),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "day_number": day_number,
        "total_days": total_days,
        "last_completed_worker": last_completed_worker,
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "workers_enabled": workers_enabled,
        "workers_disabled": workers_disabled,
    }
    with open(_state_path(), "w") as f:
        json.dump(state, f, indent=2)


def read_state() -> dict:
    """Read and return the simulation state dict, or empty dict if missing."""
    path = _state_path()
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)
