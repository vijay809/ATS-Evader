"""Human-controlled ATS analysis workspace."""

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

from openclaw.core.runtime import Runtime
from openclaw.core.tasks import TaskStatus
from openclaw.plugins.ats import (
    ATS_ANALYZER_SERVICE,
    AtsAnalysis,
    AtsAnalysisError,
    AtsAnalyzer,
    TailoredResume,
)
from openclaw.plugins.ollama import OllamaUnavailableError


class AtsWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, analyzer: AtsAnalyzer, resume: str, job_description: str, model: str) -> None:
        super().__init__()
        self._analyzer = analyzer
        self._resume = resume
        self._job_description = job_description
        self._model = model

    def run(self) -> None:
        try:
            analysis = asyncio.run(
                self._analyzer.analyze(self._resume, self._job_description, model=self._model)
            )
        except (AtsAnalysisError, OllamaUnavailableError, ValueError) as error:
            self.failed.emit(str(error))
            return
        self.completed.emit(analysis)


class TailorWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, analyzer: AtsAnalyzer, resume: str, job_description: str, model: str) -> None:
        super().__init__()
        self._analyzer = analyzer
        self._resume = resume
        self._job_description = job_description
        self._model = model

    def run(self) -> None:
        try:
            result = asyncio.run(
                self._analyzer.tailor(self._resume, self._job_description, model=self._model)
            )
        except (AtsAnalysisError, OllamaUnavailableError, ValueError) as error:
            self.failed.emit(str(error))
            return
        self.completed.emit(result)


class AtsWorkspace(QWidget):
    """Paste-in resume analysis; users review every recommendation before acting on it."""

    def __init__(self, runtime: Runtime) -> None:
        super().__init__()
        self._runtime = runtime
        self._task_id: UUID | None = None
        self._worker: QThread | None = None

        self._model = QLineEdit("gemma4:12b")
        self._resume = QPlainTextEdit()
        self._resume.setPlaceholderText("Paste the resume text here...")
        self._job_description = QPlainTextEdit()
        self._job_description.setPlaceholderText("Paste the job description here...")
        self._result = QPlainTextEdit()
        self._result.setReadOnly(True)
        self._status = QLabel("Paste both documents, then run a local analysis.")
        self._analyze_button = QPushButton("Analyze locally")
        self._analyze_button.clicked.connect(self.analyze)
        self._tailor_button = QPushButton("Tailor resume locally")
        self._tailor_button.clicked.connect(self.tailor)

        form = QFormLayout()
        form.addRow("Model", self._model)
        form.addRow("Resume", self._resume)
        form.addRow("Job description", self._job_description)
        controls = QHBoxLayout()
        controls.addWidget(self._analyze_button)
        controls.addWidget(self._tailor_button)
        controls.addWidget(self._status)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(controls)
        layout.addWidget(QLabel("ATS analysis"))
        layout.addWidget(self._result)

    def analyze(self) -> None:
        resume = self._resume.toPlainText().strip()
        job_description = self._job_description.toPlainText().strip()
        model = self._model.text().strip()
        if not resume or not job_description or not model:
            self._set_status("Enter a model, resume, and job description.")
            return
        try:
            analyzer = self._runtime.services.get(ATS_ANALYZER_SERVICE)
        except LookupError:
            self._set_status("The ATS plugin is unavailable.")
            return
        if not isinstance(analyzer, AtsAnalyzer):
            self._set_status("The registered ATS service is invalid.")
            return

        task = asyncio.run(self._runtime.tasks.create("Analyze resume against job description"))
        asyncio.run(self._runtime.tasks.transition(task.id, TaskStatus.RUNNING, model))
        self._task_id = task.id
        self._result.clear()
        self._analyze_button.setEnabled(False)
        self._set_status("Analyzing locally...")
        self._worker = AtsWorker(analyzer, resume, job_description, model)
        self._worker.completed.connect(self._show_analysis)
        self._worker.failed.connect(self._show_failure)
        self._worker.start()

    def tailor(self) -> None:
        resume = self._resume.toPlainText().strip()
        job_description = self._job_description.toPlainText().strip()
        model = self._model.text().strip()
        if not resume or not job_description or not model:
            self._set_status("Enter a model, resume, and job description.")
            return
        try:
            analyzer = self._runtime.services.get(ATS_ANALYZER_SERVICE)
        except LookupError:
            self._set_status("The ATS plugin is unavailable.")
            return
        if not isinstance(analyzer, AtsAnalyzer):
            self._set_status("The registered ATS service is invalid.")
            return

        task = asyncio.run(self._runtime.tasks.create("Tailor resume for job description"))
        asyncio.run(self._runtime.tasks.transition(task.id, TaskStatus.RUNNING, model))
        self._task_id = task.id
        self._result.clear()
        self._analyze_button.setEnabled(False)
        self._tailor_button.setEnabled(False)
        self._set_status("Tailoring locally. Review every change before using it.")
        self._worker = TailorWorker(analyzer, resume, job_description, model)
        self._worker.completed.connect(self._show_tailoring)
        self._worker.failed.connect(self._show_failure)
        self._worker.start()

    def _show_analysis(self, result: object) -> None:
        if not isinstance(result, AtsAnalysis):
            self._show_failure("The ATS plugin returned an invalid result.")
            return
        matched = ", ".join(result.matched_keywords) or "None identified"
        missing = ", ".join(result.missing_keywords) or "None identified"
        recommendations = "\n".join(f"- {item}" for item in result.recommendations) or "- None"
        self._result.setPlainText(
            f"Match score: {result.match_score}/100\n\n"
            f"Summary\n{result.summary}\n\n"
            f"Matched keywords\n{matched}\n\n"
            f"Missing keywords\n{missing}\n\n"
            f"Recommendations\n{recommendations}"
        )
        self._finish(TaskStatus.SUCCEEDED, f"Match score: {result.match_score}/100")
        self._set_status("Analysis complete. Review recommendations before editing your resume.")

    def _show_tailoring(self, result: object) -> None:
        if not isinstance(result, TailoredResume):
            self._show_failure("The ATS plugin returned an invalid tailored resume.")
            return
        changes = "\n".join(f"- {item}" for item in result.change_summary) or "- None"
        warnings = "\n".join(f"- {item}" for item in result.warnings) or "- None"
        self._result.setPlainText(
            f"Tailored resume draft\n\n{result.tailored_resume}\n\n"
            f"Change summary\n{changes}\n\n"
            f"Warnings — verify before use\n{warnings}"
        )
        self._finish(TaskStatus.SUCCEEDED, "Tailored resume draft ready for review")
        self._set_status("Draft ready. Verify all content before using it.")

    def _show_failure(self, message: str) -> None:
        self._finish(TaskStatus.FAILED, message)
        self._set_status(f"Analysis failed: {message}")

    def _finish(self, status: TaskStatus, detail: str) -> None:
        if self._task_id is not None:
            asyncio.run(self._runtime.tasks.transition(self._task_id, status, detail))
            self._task_id = None
        self._analyze_button.setEnabled(True)
        self._tailor_button.setEnabled(True)
        self._worker = None

    def _set_status(self, message: str) -> None:
        self._status.setText(message)
