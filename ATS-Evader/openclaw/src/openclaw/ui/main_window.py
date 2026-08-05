"""Desktop shell and monitoring surface for the local runtime."""

from __future__ import annotations

import asyncio
from datetime import UTC
from uuid import UUID

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QWidget,
)

from openclaw.core.events import RuntimeEvent
from openclaw.core.runtime import Runtime
from openclaw.core.tasks import TaskStatus
from openclaw.ui.ai_workspace import AiWorkspace
from openclaw.ui.ats_workspace import AtsWorkspace
from openclaw.ui.job_search_workspace import JobSearchWorkspace
from openclaw.ui.monitor import task_rows


class MainWindow(QMainWindow):
    """Read-only monitoring UI; task execution remains owned by the runtime."""

    event_received = Signal(object)

    def __init__(self, runtime: Runtime) -> None:
        super().__init__()
        self._runtime = runtime
        self.setWindowTitle("OpenClaw")
        self.setMinimumSize(1000, 650)

        self._tasks_table = QTableWidget(0, 4)
        self._tasks_table.setHorizontalHeaderLabels(["ID", "Task", "Status", "Detail"])
        self._tasks_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tasks_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setCentralWidget(self._tasks_table)

        self._task_name = QLineEdit()
        self._task_name.setPlaceholderText("Describe a task...")
        self._task_name.returnPressed.connect(self.create_task)
        self._status_selector = QComboBox()
        self._status_selector.addItem("Start", TaskStatus.RUNNING)
        self._status_selector.addItem("Complete", TaskStatus.SUCCEEDED)
        self._status_selector.addItem("Fail", TaskStatus.FAILED)
        self._status_selector.addItem("Cancel", TaskStatus.CANCELLED)
        self._build_task_toolbar()

        self._activity = QPlainTextEdit()
        self._activity.setReadOnly(True)
        activity_dock = QDockWidget("Activity", self)
        activity_dock.setWidget(self._activity)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, activity_dock)

        ai_dock = QDockWidget("Local AI", self)
        ai_dock.setWidget(AiWorkspace(runtime))
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, ai_dock)
        
        job_search_dock = QDockWidget("Job Search", self)
        job_search_dock.setWidget(JobSearchWorkspace(runtime))
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, job_search_dock)

        ats_dock = QDockWidget("ATS analysis", self)
        ats_dock.setWidget(AtsWorkspace(runtime))
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, ats_dock)

        self.event_received.connect(self._record_event)
        self._runtime.events.subscribe("task.changed", self._on_task_changed)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(500)
        self._refresh_timer.timeout.connect(self.refresh_tasks)
        self._refresh_timer.start()
        self.refresh_tasks()

    def _build_task_toolbar(self) -> None:
        toolbar = QToolBar("Task controls", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        create_group = QWidget()
        create_layout = QHBoxLayout(create_group)
        create_layout.setContentsMargins(4, 0, 4, 0)
        create_layout.addWidget(QLabel("New task"))
        create_layout.addWidget(self._task_name)
        create_button = QPushButton("Create")
        create_button.clicked.connect(self.create_task)
        create_layout.addWidget(create_button)
        toolbar.addWidget(create_group)

        toolbar.addSeparator()
        toolbar.addWidget(QLabel("Selected task"))
        toolbar.addWidget(self._status_selector)
        update_button = QPushButton("Apply")
        update_button.clicked.connect(self.update_selected_task)
        toolbar.addWidget(update_button)

    async def _on_task_changed(self, event: RuntimeEvent) -> None:
        self.event_received.emit(event)

    def refresh_tasks(self) -> None:
        rows = task_rows(self._runtime.tasks.all())
        self._tasks_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column, value in enumerate((row.identifier, row.name, row.status, row.detail)):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row.task_id)
                self._tasks_table.setItem(row_index, column, item)
        self._tasks_table.resizeColumnsToContents()

    def create_task(self) -> None:
        name = self._task_name.text().strip()
        if not name:
            self._record_message("Enter a task description before creating it.")
            return
        asyncio.run(self._runtime.tasks.create(name))
        self._task_name.clear()
        self.refresh_tasks()

    def update_selected_task(self) -> None:
        row = self._tasks_table.currentRow()
        if row < 0:
            self._record_message("Select a task before changing its status.")
            return
        item = self._tasks_table.item(row, 0)
        if item is None:
            self._record_message("The selected task is unavailable. Refresh and try again.")
            return
        task_id = UUID(str(item.data(Qt.ItemDataRole.UserRole)))
        status = self._status_selector.currentData()
        if not isinstance(status, TaskStatus):
            self._record_message("Choose a valid task status.")
            return
        try:
            asyncio.run(self._runtime.tasks.transition(task_id, status))
        except ValueError as error:
            self._record_message(str(error))
            return
        self.refresh_tasks()

    def _record_event(self, event: RuntimeEvent) -> None:
        timestamp = event.occurred_at.astimezone(UTC).strftime("%H:%M:%S UTC")
        status = str(event.payload.get("status", ""))
        task_id = str(event.payload.get("task_id", ""))[:8]
        self._activity.appendPlainText(f"{timestamp}  {event.topic}  {task_id} {status}")
        self.refresh_tasks()

    def _record_message(self, message: str) -> None:
        self._activity.appendPlainText(message)
