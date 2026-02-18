"""Abstract repository interface — swap-friendly for future DB backends."""

from abc import ABC, abstractmethod
from typing import Any, List, Optional


class BaseRepository(ABC):
    """Abstract CRUD interface.  Concrete implementations use SQLAlchemy sessions."""

    @abstractmethod
    def get_by_id(self, entity_id: int) -> Optional[Any]:
        """Return a single entity by primary key, or None."""

    @abstractmethod
    def get_all(self) -> List[Any]:
        """Return every row in the table."""

    @abstractmethod
    def get_where(self, **filters) -> List[Any]:
        """Return rows matching all supplied keyword filters (AND logic)."""

    @abstractmethod
    def create(self, entity: Any) -> Any:
        """Persist a new entity and return it with its generated id."""

    @abstractmethod
    def update(self, entity: Any) -> Any:
        """Merge and persist changes to an existing entity."""

    @abstractmethod
    def delete(self, entity_id: int) -> bool:
        """Delete an entity by primary key.  Return True if deleted."""

    @abstractmethod
    def count_where(self, **filters) -> int:
        """Return the count of rows matching all supplied filters."""
