"""Abstract BaseWorker — all workers inherit from this."""

from abc import ABC, abstractmethod
from datetime import date
import random


class BaseWorker(ABC):
    name: str = ""
    enabled: bool = True

    @abstractmethod
    def run(self, sim_date: date, rng: random.Random) -> dict:
        """Execute worker logic for one simulation day.

        Returns a dict of stats to merge into the daily result snapshot.
        """
