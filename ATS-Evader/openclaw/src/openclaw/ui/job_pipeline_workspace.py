"""Unified Job Pipeline workspace for reviewing extracted jobs and managing applications."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, cast
from uuid import UUID

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)

from openclaw.core.documents import JobDescription, Resume, AnalysisResult
from openclaw.core.runtime import Runtime
from openclaw.core.tasks import TaskStatus
from openclaw.plugins.ats import ATS_ANALYZER_SERVICE, AtsAnalyzer, AtsAnalysis, TailoredResume
from openclaw.ui.ats_workspace import TailorReviewDialog, TailorWorker, AtsWorker

if TYPE_CHECKING:
    pass


class JobPipelineWorkspace(QWidget):
    """Dashboard for tracking and applying to extracted jobs."""

    def __init__(self, runtime: Runtime) -> None:
        super().__init__()
        self._runtime = runtime
        self._worker: QThread | None = None
        self._task_id: UUID | None = None
        
        # Resume Selector
        self._resume_selector = QComboBox()
        self._refresh_resumes()
        
        self._refresh_btn = QPushButton("Refresh Data")
        self._refresh_btn.clicked.connect(self._refresh_data)
        
        # Job Table
        self._job_table = QTableWidget()
        self._job_table.setColumnCount(5)
        self._job_table.setHorizontalHeaderLabels(["Company", "Title", "ATS Score", "Status", "Actions"])
        self._job_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._job_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._job_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._job_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Master Resume:"))
        top_layout.addWidget(self._resume_selector, stretch=1)
        top_layout.addWidget(self._refresh_btn)
        
        layout = QVBoxLayout(self)
        layout.addLayout(top_layout)
        layout.addWidget(QLabel("Extracted Jobs:"))
        layout.addWidget(self._job_table)
        
        self._status = QLabel("Ready.")
        layout.addWidget(self._status)
        
        self._refresh_data()

    def _refresh_resumes(self) -> None:
        self._resume_selector.clear()
        try:
            resumes = self._runtime.plugins._context.documents.list_resumes()
            for r in resumes:
                self._resume_selector.addItem(r.name, r.id)
        except AttributeError:
            pass

    def _refresh_data(self) -> None:
        self._refresh_resumes()
        self._job_table.setRowCount(0)
        
        try:
            jobs = self._runtime.plugins._context.documents.list_job_descriptions()
            for row, job in enumerate(jobs):
                self._job_table.insertRow(row)
                
                # We attempt to extract Title and Company from the name if formatted as 'Title at Company'
                # But JobDescription.name doesn't strictly enforce this. By default extract_naukri_jd creates a specific name?
                # Let's just use the job name for Title, or split it.
                title = job.name
                company = "Unknown"
                if " at " in job.name:
                    parts = job.name.split(" at ", 1)
                    title, company = parts[0], parts[1]
                    
                self._job_table.setItem(row, 0, QTableWidgetItem(company))
                self._job_table.setItem(row, 1, QTableWidgetItem(title))
                
                # Fetch ATS Score
                latest_analysis = self._runtime.plugins._context.documents.get_latest_analysis(str(job.id))
                score_str = f"{latest_analysis.match_score}/100" if latest_analysis else "N/A"
                self._job_table.setItem(row, 2, QTableWidgetItem(score_str))
                
                self._job_table.setItem(row, 3, QTableWidgetItem(job.status))
                
                # Actions Widget
                action_widget = QWidget()
                action_layout = QHBoxLayout(action_widget)
                action_layout.setContentsMargins(2, 2, 2, 2)
                
                analyze_btn = QPushButton("Analyze")
                analyze_btn.clicked.connect(lambda checked=False, j_id=job.id: self._analyze_job(j_id))
                
                tailor_btn = QPushButton("Tailor")
                tailor_btn.clicked.connect(lambda checked=False, j_id=job.id: self._tailor_job(j_id))
                
                apply_btn = QPushButton("Apply (Agent)")
                apply_btn.clicked.connect(lambda checked=False, j_id=job.id: self._apply_job(j_id))
                
                action_layout.addWidget(analyze_btn)
                action_layout.addWidget(tailor_btn)
                action_layout.addWidget(apply_btn)
                
                self._job_table.setCellWidget(row, 4, action_widget)
        except AttributeError:
            self._status.setText("Database is not ready.")

    def _get_selected_resume(self) -> Resume | None:
        idx = self._resume_selector.currentIndex()
        if idx < 0:
            return None
        r_id = self._resume_selector.itemData(idx)
        return self._runtime.plugins._context.documents.get_resume(str(r_id))

    def _analyze_job(self, job_id: UUID) -> None:
        resume = self._get_selected_resume()
        if not resume:
            QMessageBox.warning(self, "Error", "Please import and select a Master Resume first.")
            return
            
        job = self._runtime.plugins._context.documents.get_job_description(str(job_id))
        if not job:
            return
            
        try:
            analyzer = self._runtime.services.get(ATS_ANALYZER_SERVICE)
        except LookupError:
            self._status.setText("ATS plugin is unavailable.")
            return

        self._status.setText(f"Analyzing {job.name}...")
        self._worker = AtsWorker(cast(AtsAnalyzer, analyzer), resume.content, job.content, "gemma4:12b")
        # Overriding completed to persist correctly
        self._worker.completed.connect(lambda res: self._on_analysis_complete(res, resume, job))
        self._worker.failed.connect(lambda err: self._status.setText(f"Analysis Failed: {err}"))
        self._worker.start()

    def _on_analysis_complete(self, result: object, resume: Resume, jd: JobDescription) -> None:
        if not hasattr(result, "match_score"):
            return
            
        analysis_result = cast(AtsAnalysis, result)
        record = AnalysisResult(
            resume_id=resume.id,
            job_id=jd.id,
            match_score=analysis_result.match_score,
            matched_keywords=",".join(analysis_result.matched_keywords),
            missing_keywords=",".join(analysis_result.missing_keywords),
            recommendations="\n".join(analysis_result.recommendations),
            summary=analysis_result.summary
        )
        self._runtime.plugins._context.documents.save_analysis(record)
        
        # Update status and refresh table
        jd.status = "Analyzed"
        self._runtime.plugins._context.documents.save_job_description(jd)
        self._status.setText(f"Analysis complete for {jd.name}: Score {analysis_result.match_score}")
        self._refresh_data()

    def _tailor_job(self, job_id: UUID) -> None:
        resume = self._get_selected_resume()
        if not resume:
            QMessageBox.warning(self, "Error", "Please select a Master Resume.")
            return
            
        job = self._runtime.plugins._context.documents.get_job_description(str(job_id))
        if not job:
            return
            
        try:
            analyzer = self._runtime.services.get(ATS_ANALYZER_SERVICE)
        except LookupError:
            self._status.setText("ATS plugin is unavailable.")
            return

        self._status.setText(f"Tailoring {job.name}...")
        self._worker = TailorWorker(cast(AtsAnalyzer, analyzer), resume.content, job.content, "gemma4:12b")
        self._worker.completed.connect(lambda res: self._on_tailor_complete(res, resume, job))
        self._worker.failed.connect(lambda err: self._status.setText(f"Tailoring Failed: {err}"))
        self._worker.start()

    def _on_tailor_complete(self, result: object, resume: Resume, jd: JobDescription) -> None:
        if not hasattr(result, "tailored_resume"):
            return
            
        tailored_result = cast(TailoredResume, result)
        dialog = TailorReviewDialog(resume.content, tailored_result, self)
        if dialog.exec():
            final_content = dialog.tailored_text.toPlainText()
            from openclaw.core.documents import TailoredDraft
            draft = TailoredDraft(
                resume_id=resume.id,
                job_id=jd.id,
                content=final_content,
                change_summary=",".join(tailored_result.change_summary),
                warnings=",".join(tailored_result.warnings)
            )
            self._runtime.plugins._context.documents.save_draft(draft)
            
            jd.status = "Tailored"
            self._runtime.plugins._context.documents.save_job_description(jd)
            self._status.setText(f"Saved tailored resume for {jd.name}.")
            self._refresh_data()
        else:
            self._status.setText("Tailored resume discarded.")

    def _apply_job(self, job_id: UUID) -> None:
        # In a full continuous loop, this would orchestrate SemanticNavigator repeatedly.
        # For this prototype step, we open the URL in the browser.
        job = self._runtime.plugins._context.documents.get_job_description(str(job_id))
        if not job or not job.url:
            QMessageBox.warning(self, "Error", "Job URL is not available. Please navigate manually.")
            return
            
        try:
            from openclaw.plugins.browser import BrowserService, BROWSER_SERVICE
            browser = self._runtime.services.get(BROWSER_SERVICE)
            if isinstance(browser, BrowserService):
                task = asyncio.run(self._runtime.tasks.create(f"Applying to {job.name}"))
                asyncio.run(self._runtime.tasks.transition(task.id, TaskStatus.RUNNING, "Opening browser..."))
                
                # Launch async
                def run_launch() -> None:
                    asyncio.run(browser.launch(job.url))
                    
                import threading
                t = threading.Thread(target=run_launch)
                t.start()
                
                job.status = "Applying"
                self._runtime.plugins._context.documents.save_job_description(job)
                self._refresh_data()
                self._status.setText(f"Opening {job.url} in browser...")
                asyncio.run(self._runtime.tasks.transition(task.id, TaskStatus.SUCCEEDED, "Browser launched"))
        except LookupError:
            self._status.setText("Browser plugin is unavailable.")
