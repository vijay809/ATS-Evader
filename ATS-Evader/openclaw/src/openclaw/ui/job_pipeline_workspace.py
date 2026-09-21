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
    QScrollArea,
    QFrame,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)

from openclaw.core.documents import JobDescription, Resume, AnalysisResult
from openclaw.core.runtime import Runtime
from openclaw.core.tasks import TaskStatus
from openclaw.plugins.ats import ATS_ANALYZER_SERVICE, AtsAnalyzer, AtsAnalysis, TailoredResume


if TYPE_CHECKING:
    pass


class JobPipelineWorkspace(QWidget):
    """Dashboard for tracking and applying to extracted jobs using a Kanban board."""

    def __init__(self, runtime: Runtime) -> None:
        super().__init__()
        self._runtime = runtime
        self._worker: QThread | None = None
        
        # Resume Selector
        self._resume_selector = QComboBox()
        self._refresh_resumes()
        
        self._refresh_btn = QPushButton("Refresh Data")
        self._refresh_btn.clicked.connect(self._refresh_data)
        
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Master Resume:"))
        top_layout.addWidget(self._resume_selector, stretch=1)
        top_layout.addWidget(self._refresh_btn)
        
        layout = QVBoxLayout(self)
        layout.addLayout(top_layout)
        
        # Kanban Board Layout
        self._kanban_layout = QHBoxLayout()
        self.columns = {}
        
        for col_name in ["Analyzed", "Applying", "Applied", "Skipped"]:
            col_widget = QWidget()
            col_widget.setStyleSheet("background-color: #1a1a1a; border-radius: 8px; border: 1px solid #333;")
            col_layout = QVBoxLayout(col_widget)
            col_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
            
            header = QLabel(col_name)
            header.setStyleSheet("font-size: 18px; font-weight: bold; color: #adc6ff; padding: 8px; border: none;")
            col_layout.addWidget(header)
            
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setStyleSheet("border: none; background: transparent;")
            
            inner_widget = QWidget()
            inner_widget.setStyleSheet("background: transparent;")
            inner_layout = QVBoxLayout(inner_widget)
            inner_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
            scroll.setWidget(inner_widget)
            
            col_layout.addWidget(scroll)
            
            self._kanban_layout.addWidget(col_widget)
            self.columns[col_name] = inner_layout
            
        layout.addLayout(self._kanban_layout)
        
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
        
        # Clear Kanban columns
        for layout in self.columns.values():
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
                    
        try:
            jobs = self._runtime.plugins._context.documents.list_job_descriptions()
            for job in jobs:
                title = job.name
                company = "Unknown"
                if " at " in job.name:
                    parts = job.name.split(" at ", 1)
                    title, company = parts[0], parts[1]
                    
                latest_analysis = self._runtime.plugins._context.documents.get_latest_analysis(str(job.id))
                score_str = f"{latest_analysis.match_score}%" if latest_analysis else "N/A"
                
                # Determine target column
                status = job.status
                if status not in self.columns:
                    # Map unknown statuses to Analyzed or Skipped
                    status = "Analyzed"
                    
                target_layout = self.columns[status]
                
                # Build Card
                from PySide6.QtWidgets import QFrame
                card = QFrame()
                card.setStyleSheet("background-color: #2a2a2a; border-radius: 6px; border: 1px solid #444; margin-bottom: 8px;")
                card_layout = QVBoxLayout(card)
                
                title_lbl = QLabel(title)
                title_lbl.setStyleSheet("font-weight: bold; color: white; font-size: 14px; border: none;")
                title_lbl.setWordWrap(True)
                
                comp_lbl = QLabel(f"{company} | Score: {score_str}")
                comp_lbl.setStyleSheet("color: #aaa; font-size: 12px; border: none;")
                
                card_layout.addWidget(title_lbl)
                card_layout.addWidget(comp_lbl)
                
                # Actions based on status
                action_layout = QHBoxLayout()
                
                if job.url:
                    open_btn = QPushButton("Open Link")
                    open_btn.setStyleSheet("background-color: #333; color: white; border-radius: 4px; padding: 4px;")
                    open_btn.clicked.connect(lambda checked=False, u=job.url: self._open_url(u))
                    action_layout.addWidget(open_btn)
                
                if status == "Analyzed":
                    apply_btn = QPushButton("Apply")
                    apply_btn.setStyleSheet("background-color: #4b8eff; color: white; border-radius: 4px; padding: 4px;")
                    apply_btn.clicked.connect(lambda checked=False, j=job: self._move_job(j, "Applying"))
                    action_layout.addWidget(apply_btn)
                    
                    skip_btn = QPushButton("Skip")
                    skip_btn.setStyleSheet("background-color: #555; color: white; border-radius: 4px; padding: 4px;")
                    skip_btn.clicked.connect(lambda checked=False, j=job: self._move_job(j, "Skipped"))
                    action_layout.addWidget(skip_btn)
                    
                elif status == "Applying":
                    done_btn = QPushButton("Mark Applied")
                    done_btn.setStyleSheet("background-color: #3b5a4b; color: white; border-radius: 4px; padding: 4px;")
                    done_btn.clicked.connect(lambda checked=False, j=job: self._move_job(j, "Applied"))
                    action_layout.addWidget(done_btn)
                
                if action_layout.count() > 0:
                    card_layout.addLayout(action_layout)
                    
                target_layout.addWidget(card)
                
        except AttributeError:
            self._status.setText("Database is not ready.")

    def _move_job(self, job: JobDescription, new_status: str) -> None:
        job.status = new_status
        self._runtime.plugins._context.documents.save_job_description(job)
        self._refresh_data()

    def _open_url(self, url: str) -> None:
        import webbrowser
        webbrowser.open(url)
