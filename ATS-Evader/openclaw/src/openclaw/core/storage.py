"""SQLite persistence owned by the runtime.

Plugins receive higher-level services instead of direct database access. This keeps schema
ownership, migrations, and data retention decisions at the runtime boundary.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from sqlmodel import Field, Session, SQLModel, create_engine, select

if TYPE_CHECKING:
    from openclaw.core.tasks import Task


class TaskRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    status: str
    detail: str | None = None


class TaskRepository(Protocol):
    def save(self, task: Task) -> None: ...

    def list(self) -> Iterable[Task]: ...


class SQLiteTaskRepository:
    """Small repository adapter that makes task persistence replaceable and testable."""

    def __init__(self, database_path: Path) -> None:
        self._engine = create_engine(f"sqlite:///{database_path}")

    def initialize(self) -> None:
        SQLModel.metadata.create_all(self._engine)

    def save(self, task: Task) -> None:
        record = TaskRecord(
            id=str(task.id),
            name=task.name,
            status=task.status.value,
            detail=task.detail,
        )
        with Session(self._engine) as session:
            session.merge(record)
            session.commit()

    def list(self) -> Iterable[Task]:
        from uuid import UUID

        from openclaw.core.tasks import Task, TaskStatus

        with Session(self._engine) as session:
            records = session.exec(select(TaskRecord).order_by(TaskRecord.name)).all()
        return tuple(
            Task(
                id=UUID(record.id),
                name=record.name,
                status=TaskStatus(record.status),
                detail=record.detail,
            )
            for record in records
        )
