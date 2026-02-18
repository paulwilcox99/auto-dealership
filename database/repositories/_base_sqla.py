"""Shared SQLAlchemy implementation of BaseRepository."""

from typing import Any, List, Optional, Type

from sqlalchemy.orm import Session

from database.base import BaseRepository


class SQLARepository(BaseRepository):
    """Generic SQLAlchemy implementation.  Subclasses set `model_class` and `session`."""

    model_class: Type[Any] = None

    def __init__(self, session: Session):
        self.session = session

    # ── BaseRepository interface ──────────────────────────────────────────────

    def get_by_id(self, entity_id: int) -> Optional[Any]:
        return self.session.get(self.model_class, entity_id)

    def get_all(self) -> List[Any]:
        return self.session.query(self.model_class).all()

    def get_where(self, **filters) -> List[Any]:
        q = self.session.query(self.model_class)
        for attr, value in filters.items():
            q = q.filter(getattr(self.model_class, attr) == value)
        return q.all()

    def create(self, entity: Any) -> Any:
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)
        return entity

    def update(self, entity: Any) -> Any:
        merged = self.session.merge(entity)
        self.session.commit()
        return merged

    def delete(self, entity_id: int) -> bool:
        obj = self.get_by_id(entity_id)
        if obj is None:
            return False
        self.session.delete(obj)
        self.session.commit()
        return True

    def count_where(self, **filters) -> int:
        q = self.session.query(self.model_class)
        for attr, value in filters.items():
            q = q.filter(getattr(self.model_class, attr) == value)
        return q.count()

    # ── Convenience helpers (used across workers) ─────────────────────────────

    def get_first_where(self, **filters) -> Optional[Any]:
        q = self.session.query(self.model_class)
        for attr, value in filters.items():
            q = q.filter(getattr(self.model_class, attr) == value)
        return q.first()

    def bulk_create(self, entities: List[Any]) -> List[Any]:
        self.session.add_all(entities)
        self.session.commit()
        return entities
