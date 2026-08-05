from uuid import UUID

from openclaw.core.tasks import Task, TaskStatus
from openclaw.ui.monitor import task_rows


def test_task_rows_are_sorted_and_display_friendly() -> None:
    rows = task_rows(
        (
            Task(id=UUID(int=1), name="Zebra", status=TaskStatus.PENDING),
            Task(id=UUID(int=2), name="Analyze CV", status=TaskStatus.RUNNING, detail="Reading"),
        )
    )

    assert [(row.name, row.status, row.detail) for row in rows] == [
        ("Analyze CV", "Running", "Reading"),
        ("Zebra", "Pending", ""),
    ]
