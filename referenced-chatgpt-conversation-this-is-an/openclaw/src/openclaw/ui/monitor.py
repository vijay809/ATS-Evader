"""Presentation-ready task snapshots for the desktop monitor."""

from dataclasses import dataclass

from openclaw.core.tasks import Task


@dataclass(frozen=True, slots=True)
class TaskRow:
    task_id: str
    identifier: str
    name: str
    status: str
    detail: str


def task_rows(tasks: tuple[Task, ...]) -> tuple[TaskRow, ...]:
    """Map runtime task state to stable table values without Qt dependencies."""
    return tuple(
        TaskRow(
            task_id=str(task.id),
            identifier=str(task.id)[:8],
            name=task.name,
            status=task.status.value.title(),
            detail=task.detail or "",
        )
        for task in sorted(tasks, key=lambda item: item.name.casefold())
    )
