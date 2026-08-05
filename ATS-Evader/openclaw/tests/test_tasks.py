from pathlib import Path

from openclaw.core.events import EventBus
from openclaw.core.storage import SQLiteTaskRepository
from openclaw.core.tasks import TaskManager, TaskStatus


async def test_task_changes_publish_events(tmp_path: Path) -> None:
    events = EventBus()
    received: list[str] = []

    async def collect(event: object) -> None:
        received.append(str(event))

    events.subscribe("task.changed", collect)
    repository = SQLiteTaskRepository(tmp_path / "tasks.sqlite")
    repository.initialize()
    tasks = TaskManager(events, repository)
    task = await tasks.create("check CV")
    await tasks.transition(task.id, TaskStatus.RUNNING)

    assert tasks.get(task.id).status is TaskStatus.RUNNING
    assert next(iter(repository.list())).status is TaskStatus.RUNNING
    assert len(received) == 2
