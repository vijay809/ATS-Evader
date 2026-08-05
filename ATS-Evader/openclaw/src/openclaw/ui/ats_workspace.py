"""Human-controlled ATS analysis workspace."""

from __future__ import annotations

import asyncio
from uuid import UUID

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt

from openclaw.core.documents import AnalysisResult, JobDescription, Resume, TailoredDraft
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


class TailorReviewDialog(QDialog):
    def __init__(self, original: str, tailored: TailoredResume, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Review Tailored Resume")
        self.resize(1000, 600)
        self.approved = False
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        orig_text = QPlainTextEdit(original)
        orig_text.setReadOnly(True)
        
        self.tailored_text = QPlainTextEdit(tailored.tailored_resume)
        
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("Original Resume"))
        left_layout.addWidget(orig_text)
        left_widget = QWidget()
        left_widget.setLayout(left_layout)
        
        right_layout = QVBoxLayout()
        right_layout.addWidget(QLabel("Tailored Draft (Editable)"))
        right_layout.addWidget(self.tailored_text)
        
        changes = "\n".join(f"- {item}" for item in tailored.change_summary) or "- None"
        warnings = "\n".join(f"- {item}" for item in tailored.warnings) or "- None"
        info = QPlainTextEdit(f"Changes:\n{changes}\n\nWarnings:\n{warnings}")
        info.setReadOnly(True)
        right_layout.addWidget(QLabel("Summary & Warnings"))
        right_layout.addWidget(info)
        
        right_widget = QWidget()
        right_widget.setLayout(right_layout)
        
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        
        controls = QHBoxLayout()
        approve_btn = QPushButton("Approve and Save")
        approve_btn.clicked.connect(self.approve)
        cancel_btn = QPushButton("Discard")
        cancel_btn.clicked.connect(self.reject)
        controls.addStretch()
        controls.addWidget(cancel_btn)
        controls.addWidget(approve_btn)
        
        layout = QVBoxLayout(self)
        layout.addWidget(splitter)
        layout.addLayout(controls)

    def approve(self) -> None:
        self.approved = True
        self.accept()


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
        self._import_resume_btn = QPushButton("Import Resume")
        self._import_resume_btn.clicked.connect(self.import_resume)
        self._import_jd_btn = QPushButton("Import JD")
        self._import_jd_btn.clicked.connect(self.import_jd)

        form = QFormLayout()
        form.addRow("Model", self._model)
        
        resume_layout = QVBoxLayout()
        resume_layout.addWidget(self._import_resume_btn)
        resume_layout.addWidget(self._resume)
        
        jd_layout = QVBoxLayout()
        jd_layout.addWidget(self._import_jd_btn)
        jd_layout.addWidget(self._job_description)

        form.addRow("Resume", resume_layout)
        form.addRow("Job description", jd_layout)
        controls = QHBoxLayout()
        controls.addWidget(self._analyze_button)
        controls.addWidget(self._tailor_button)
        controls.addWidget(self._status)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(controls)
        layout.addWidget(QLabel("ATS analysis"))
        layout.addWidget(self._result)

    def import_resume(self) -> None:
        self._import_document(self._resume)

    def import_jd(self) -> None:
        self._import_document(self._job_description)

    def _import_document(self, text_edit: QPlainTextEdit) -> None:
        try:
            from openclaw.plugins.documents import DOCUMENTS_SERVICE, DocumentIngestionService
            service = self._runtime.services.get(DOCUMENTS_SERVICE)
            if not isinstance(service, DocumentIngestionService):
                self._set_status("Document ingestion service is invalid.")
                return
        except LookupError:
            self._set_status("Document ingestion plugin is not available.")
            return

        file_path, _ = QFileDialog.getOpenFileName(self, "Open Document", "", "Documents (*.pdf *.docx *.txt *.md)")
        if file_path:
            try:
                text = service.read_text(file_path)
                text_edit.setPlainText(text)
                self._set_status(f"Imported document: {file_path}")
            except Exception as error:
                self._show_failure(f"Failed to import: {error}")

    def _persist_inputs(self, resume_text: str, jd_text: str) -> tuple[Resume, JobDescription]:
        resume = Resume(content=resume_text)
        jd = JobDescription(content=jd_text)
        self._runtime.plugins._context.documents.save_resume(resume)
        self._runtime.plugins._context.documents.save_job_description(jd)
        return resume, jd

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
        
        # Persist analysis
        resume, jd = self._persist_inputs(self._resume.toPlainText().strip(), self._job_description.toPlainText().strip())
        record = AnalysisResult(
            resume_id=resume.id,
            job_id=jd.id,
            match_score=result.match_score,
            matched_keywords=",".join(result.matched_keywords),
            missing_keywords=",".join(result.missing_keywords),
            recommendations="\n".join(result.recommendations),
            summary=result.summary
        )
        self._runtime.plugins._context.documents.save_analysis(record)

    def _show_tailoring(self, result: object) -> None:
        if not isinstance(result, TailoredResume):
            self._show_failure("The ATS plugin returned an invalid tailored resume.")
            return
        
        resume_text = self._resume.toPlainText().strip()
        dialog = TailorReviewDialog(resume_text, result, self)
        
        if dialog.exec():
            # Approved
            final_content = dialog.tailored_text.toPlainText()
            changes = "\n".join(f"- {item}" for item in result.change_summary) or "- None"
            warnings = "\n".join(f"- {item}" for item in result.warnings) or "- None"
            
            self._result.setPlainText(
                f"Tailored resume draft (APPROVED)\n\n{final_content}\n\n"
                f"Change summary\n{changes}\n\n"
                f"Warnings\n{warnings}"
            )
            
            # Persist draft
            resume, jd = self._persist_inputs(resume_text, self._job_description.toPlainText().strip())
            draft = TailoredDraft(
                resume_id=resume.id,
                job_id=jd.id,
                content=final_content,
                change_summary=",".join(result.change_summary),
                warnings=",".join(result.warnings)
            )
            self._runtime.plugins._context.documents.save_draft(draft)
            
            self._finish(TaskStatus.SUCCEEDED, "Tailored resume draft approved and saved")
            self._set_status("Draft approved and saved.")
        else:
            self._finish(TaskStatus.CANCELLED, "Tailored resume draft discarded")
            self._set_status("Draft discarded.")

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
