"""Workspace for controlling the agentic browser to search and extract jobs."""

from __future__ import annotations

import asyncio
from uuid import UUID

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from openclaw.core.documents import JobDescription
from openclaw.core.runtime import Runtime
from openclaw.core.tasks import TaskStatus
from openclaw.plugins.browser import BROWSER_SERVICE, BrowserService


class BrowserWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, service: BrowserService, url: str) -> None:
        super().__init__()
        self._service = service
        self._url = url

    def run(self) -> None:
        try:
            # First ensure browser is launched
            asyncio.run(self._service.launch())
            
            # Extract JD
            result = asyncio.run(self._service.extract_naukri_jd(self._url))
        except Exception as error:
            self.failed.emit(str(error))
            return
        self.completed.emit(result)


class LaunchBrowserWorker(QThread):
    completed = Signal()
    failed = Signal(str)

    def __init__(self, service: BrowserService) -> None:
        super().__init__()
        self._service = service

    def run(self) -> None:
        try:
            asyncio.run(self._service.launch())
        except Exception as error:
            self.failed.emit(str(error))
            return
        self.completed.emit()


class JobSearchWorkspace(QWidget):
    """UI for managing Playwright session and job search."""

    def __init__(self, runtime: Runtime) -> None:
        super().__init__()
        self._runtime = runtime
        self._worker: QThread | None = None
        self._task_id: UUID | None = None

        self._url_input = QLineEdit("https://www.naukri.com/python-developer-jobs")
        self._status = QLabel("Ready. Launch the browser or click Extract.")
        
        self._launch_button = QPushButton("Launch Browser")
        self._launch_button.clicked.connect(self.launch_browser)
        
        self._extract_button = QPushButton("Extract JD (Naukri)")
        self._extract_button.clicked.connect(self.extract_jd)

        form = QFormLayout()
        form.addRow("Target URL", self._url_input)
        
        controls = QHBoxLayout()
        controls.addWidget(self._launch_button)
        controls.addWidget(self._extract_button)
        controls.addWidget(self._status)
        
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(controls)
        layout.addStretch()

    def launch_browser(self) -> None:
        try:
            service = self._runtime.services.get(BROWSER_SERVICE)
        except LookupError:
            self._set_status("Browser plugin is unavailable.")
            return
            
        if not isinstance(service, BrowserService):
            self._set_status("Invalid browser service.")
            return

        self._set_status("Launching browser...")
        self._launch_button.setEnabled(False)
        self._worker = LaunchBrowserWorker(service)
        self._worker.completed.connect(self._on_launched)
        self._worker.failed.connect(self._show_failure)
        self._worker.start()

    def _on_launched(self) -> None:
        self._set_status("Browser launched successfully.")
        self._launch_button.setEnabled(True)
        self._worker = None

    def extract_jd(self) -> None:
        url = self._url_input.text().strip()
        if not url:
            self._set_status("Enter a URL to extract.")
            return
            
        try:
            service = self._runtime.services.get(BROWSER_SERVICE)
        except LookupError:
            self._set_status("Browser plugin is unavailable.")
            return
            
        if not isinstance(service, BrowserService):
            self._set_status("Invalid browser service.")
            return

        task = asyncio.run(self._runtime.tasks.create(f"Extract JD from {url}"))
        asyncio.run(self._runtime.tasks.transition(task.id, TaskStatus.RUNNING, "Extracting via Playwright"))
        self._task_id = task.id
        
        self._set_status("Navigating and extracting JD...")
        self._extract_button.setEnabled(False)
        
        self._worker = BrowserWorker(service, url)
        self._worker.completed.connect(self._show_extraction)
        self._worker.failed.connect(self._show_failure)
        self._worker.start()

    def _show_extraction(self, result: dict[str, str]) -> None:
        title = result.get("title", "Unknown")
        company = result.get("company", "Unknown")
        description = result.get("description", "")
        
        # Persist extracted JD
        jd = JobDescription(content=f"Title: {title}\nCompany: {company}\n\n{description}")
        self._runtime.plugins._context.documents.save_job_description(jd)
        
        self._finish(TaskStatus.SUCCEEDED, f"Extracted '{title}' at {company}")
        self._set_status(f"JD saved to database: {title} at {company}")

    def _show_failure(self, message: str) -> None:
        self._finish(TaskStatus.FAILED, message)
        self._set_status(f"Failed: {message}")

    def _finish(self, status: TaskStatus, detail: str) -> None:
        if self._task_id is not None:
            asyncio.run(self._runtime.tasks.transition(self._task_id, status, detail))
            self._task_id = None
        self._extract_button.setEnabled(True)
        self._launch_button.setEnabled(True)
        self._worker = None

    def _set_status(self, message: str) -> None:
        self._status.setText(message)
