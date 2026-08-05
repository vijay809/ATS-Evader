"""Task lifecycle tracking, independent from any execution plugin."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID, uuid4

from openclaw.core.events import EventBus, RuntimeEvent
from openclaw.core.storage import TaskRepository


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class Task:
    name: str
    id: UUID = field(default_factory=uuid4)
    status: TaskStatus = TaskStatus.PENDING
    detail: str | None = None


class TaskManager:
    def __init__(self, events: EventBus, repository: TaskRepository) -> None:
        self._events = events
        self._repository = repository
        self._tasks: dict[UUID, Task] = {}

    def get(self, task_id: UUID) -> Task:
        return self._tasks[task_id]

    def all(self) -> tuple[Task, ...]:
        return tuple(self._tasks.values())

    def restore(self, tasks: tuple[Task, ...]) -> None:
        """Restore persisted tasks during runtime startup without replaying events."""
        self._tasks = {task.id: task for task in tasks}

    async def create(self, name: str) -> Task:
        task = Task(name=name)
        self._tasks[task.id] = task
        self._repository.save(task)
        await self._notify(task)
        return task

    async def transition(self, task_id: UUID, status: TaskStatus, detail: str | None = None) -> Task:
        task = self.get(task_id)
        if task.status in {TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            raise ValueError(f"Task {task_id} is already terminal")
        task.status = status
        task.detail = detail
        self._repository.save(task)
        await self._notify(task)
        return task

    async def _notify(self, task: Task) -> None:
        await self._events.publish(
            RuntimeEvent("task.changed", {"task_id": str(task.id), "status": task.status})
        )
