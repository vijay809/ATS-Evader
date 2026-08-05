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
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from openclaw.core.documents import JobDescription
from openclaw.core.runtime import Runtime
from openclaw.core.tasks import TaskStatus
from openclaw.plugins.browser import BROWSER_SERVICE, BrowserService
from openclaw.plugins.semantic_navigator import SemanticNavigator, SemanticResult


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

    def __init__(self, service: BrowserService, url: str) -> None:
        super().__init__()
        self._service = service
        self._url = url

    def run(self) -> None:
        try:
            asyncio.run(self._service.launch(self._url))
        except Exception as error:
            self.failed.emit(str(error))
            return
        self.completed.emit()


class SemanticWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, navigator: SemanticNavigator, command: str) -> None:
        super().__init__()
        self._navigator = navigator
        self._command = command

    def run(self) -> None:
        try:
            result = asyncio.run(self._navigator.execute_command(self._command))
        except Exception as error:
            self.failed.emit(str(error))
            return
        self.completed.emit(result)


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
        
        # Semantic UI
        self._command_input = QLineEdit()
        self._command_input.setPlaceholderText("E.g., Click the search button, or Type 'Python'")
        self._command_input.returnPressed.connect(self.execute_command)
        
        self._execute_button = QPushButton("Execute")
        self._execute_button.clicked.connect(self.execute_command)
        
        self._reasoning_log = QPlainTextEdit()
        self._reasoning_log.setReadOnly(True)
        self._reasoning_log.setPlaceholderText("AI Reasoning Log...")

        form = QFormLayout()
        form.addRow("Target URL", self._url_input)
        form.addRow("Agent Command", self._command_input)
        
        controls = QHBoxLayout()
        controls.addWidget(self._launch_button)
        controls.addWidget(self._extract_button)
        controls.addWidget(self._execute_button)
        controls.addWidget(self._status)
        
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(controls)
        layout.addWidget(QLabel("AI Reasoning & Actions:"))
        layout.addWidget(self._reasoning_log)

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
        url = self._url_input.text().strip()
        self._worker = LaunchBrowserWorker(service, url)
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

    def execute_command(self) -> None:
        command = self._command_input.text().strip()
        if not command:
            self._set_status("Enter a command to execute.")
            return
            
        try:
            navigator = self._runtime.services.get("browser.navigator")
        except LookupError:
            self._set_status("Semantic Navigator is unavailable.")
            return
            
        if not isinstance(navigator, SemanticNavigator):
            self._set_status("Invalid navigator service.")
            return
            
        task = asyncio.run(self._runtime.tasks.create(f"Execute: {command}"))
        asyncio.run(self._runtime.tasks.transition(task.id, TaskStatus.RUNNING, "Agent is thinking..."))
        self._task_id = task.id
        
        self._set_status("Extracting DOM and generating action...")
        self._execute_button.setEnabled(False)
        self._command_input.setEnabled(False)
        self._command_input.clear()
        
        self._worker = SemanticWorker(navigator, command)
        self._worker.completed.connect(self._show_semantic_result)
        self._worker.failed.connect(self._show_failure)
        self._worker.start()

    def _show_semantic_result(self, result: SemanticResult) -> None:
        if result.success:
            self._reasoning_log.appendPlainText(f"--- SUCCESS ---\nReasoning: {result.reasoning}\nAction: {result.action}\n")
            self._finish(TaskStatus.SUCCEEDED, f"Executed: {result.action}")
            self._set_status(f"Executed: {result.action}")
        else:
            self._reasoning_log.appendPlainText(f"--- ERROR ---\nReasoning: {result.reasoning}\nError: {result.error}\n")
            self._finish(TaskStatus.FAILED, str(result.error))
            self._set_status("Failed to execute command.")

    def _finish(self, status: TaskStatus, detail: str) -> None:
        if self._task_id is not None:
            asyncio.run(self._runtime.tasks.transition(self._task_id, status, detail))
            self._task_id = None
        self._extract_button.setEnabled(True)
        self._launch_button.setEnabled(True)
        self._execute_button.setEnabled(True)
        self._command_input.setEnabled(True)
        self._worker = None

    def _set_status(self, message: str) -> None:
        self._status.setText(message)
