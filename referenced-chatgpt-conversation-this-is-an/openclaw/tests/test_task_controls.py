from pathlib import Path

import pytest

from openclaw.core.events import EventBus
from openclaw.core.storage import SQLiteTaskRepository
from openclaw.core.tasks import TaskManager, TaskStatus


async def test_task_can_only_transition_until_terminal(tmp_path: Path) -> None:
    repository = SQLiteTaskRepository(tmp_path / "tasks.sqlite")
    repository.initialize()
    tasks = TaskManager(EventBus(), repository)
    task = await tasks.create("Review job description")

    await tasks.transition(task.id, TaskStatus.RUNNING)
    await tasks.transition(task.id, TaskStatus.SUCCEEDED)

    with pytest.raises(ValueError, match="already terminal"):
        await tasks.transition(task.id, TaskStatus.CANCELLED)
