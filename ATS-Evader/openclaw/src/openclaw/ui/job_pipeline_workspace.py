"""Unified Job Pipeline workspace for reviewing extracted jobs and managing applications."""

from __future__ import annotations

import os
from PySide6.QtCore import Qt, QThread, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from openclaw.core.documents import JobDescription
from openclaw.core.runtime import Runtime


class JobPipelineWorkspace(QWidget):
    """Dashboard for tracking and applying to extracted jobs using a Kanban board."""

    def __init__(self, runtime: Runtime) -> None:
        super().__init__()
        self._runtime = runtime
        self._worker: QThread | None = None
        
        # Resume Selector
        self._resume_selector = QComboBox()
        self._resume_selector.setStyleSheet("""
            QComboBox {
                background-color: #ffffff;
                color: #141c29;
                border: 1px solid rgba(139, 126, 200, 0.25);
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 13px;
                font-weight: 500;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
        """)
        self._refresh_resumes()
        
        self._refresh_btn = QPushButton("Refresh Data")
        self._refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #e8e4f7;
                color: #5e5298;
                border: 1px solid rgba(94, 82, 152, 0.3);
                border-radius: 8px;
                padding: 6px 14px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #ddd7f3;
            }
        """)
        self._refresh_btn.clicked.connect(self._refresh_data)
        
        top_layout = QHBoxLayout()
        top_layout.setSpacing(12)
        top_lbl = QLabel("Master Resume:")
        top_lbl.setStyleSheet("color: #5c6479; font-size: 13px; font-weight: 600;")
        top_layout.addWidget(top_lbl)
        top_layout.addWidget(self._resume_selector, stretch=1)
        top_layout.addWidget(self._refresh_btn)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        layout.addLayout(top_layout)
        
        # Kanban Board Layout
        self._kanban_layout = QHBoxLayout()
        self._kanban_layout.setSpacing(14)
        self.columns = {}
        
        col_badge_styles = {
            "Analyzed": ("background-color: #e0f2fe; color: #1d4ed8; border: 1px solid rgba(59, 130, 246, 0.25);", "1"),
            "Ready to Apply": ("background-color: #e8e4f7; color: #5e5298; border: 1px solid rgba(94, 82, 152, 0.25);", "2"),
            "Applied": ("background-color: #e1f5ef; color: #186a59; border: 1px solid rgba(24, 106, 89, 0.25);", "3"),
            "Skipped": ("background-color: #ffdad6; color: #591b28; border: 1px solid rgba(142, 69, 85, 0.25);", "4"),
        }
        
        for col_name in ["Analyzed", "Ready to Apply", "Applied", "Skipped"]:
            col_widget = QWidget()
            col_widget.setStyleSheet("""
                QWidget {
                    background-color: #f9f9ff;
                    border-radius: 12px;
                    border: 1px solid rgba(139, 126, 200, 0.18);
                }
            """)
            col_layout = QVBoxLayout(col_widget)
            col_layout.setContentsMargins(12, 12, 12, 12)
            col_layout.setSpacing(10)
            col_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
            
            badge_style, _ = col_badge_styles.get(col_name, ("background-color: #e8e4f7; color: #5e5298;", ""))
            header = QLabel(f"  {col_name.upper()}  ")
            header.setStyleSheet(f"""
                QLabel {{
                    {badge_style}
                    font-size: 11px;
                    font-weight: 700;
                    letter-spacing: 0.5px;
                    padding: 5px 10px;
                    border-radius: 8px;
                }}
            """)
            col_layout.addWidget(header)
            
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setStyleSheet("""
                QScrollArea { border: none; background: transparent; }
                QScrollBar:vertical {
                    background: transparent;
                    width: 6px;
                    margin: 0;
                }
                QScrollBar::handle:vertical {
                    background: #d8daf0;
                    min-height: 20px;
                    border-radius: 3px;
                }
                QScrollBar::handle:vertical:hover {
                    background: #8b7ec8;
                }
            """)
            
            inner_widget = QWidget()
            inner_widget.setStyleSheet("background: transparent; border: none;")
            inner_layout = QVBoxLayout(inner_widget)
            inner_layout.setContentsMargins(0, 4, 0, 0)
            inner_layout.setSpacing(8)
            inner_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
            scroll.setWidget(inner_widget)
            
            col_layout.addWidget(scroll)
            
            self._kanban_layout.addWidget(col_widget)
            self.columns[col_name] = inner_layout
            
        layout.addLayout(self._kanban_layout)
        
        self._status = QLabel("Ready.")
        self._status.setStyleSheet("color: #8f96a8; font-size: 12px; font-weight: 500;")
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
        for col_layout in self.columns.values():
            while col_layout.count():
                child = col_layout.takeAt(0)
                if child is not None:
                    w = child.widget()
                    if w is not None:
                        w.setParent(None)
                        w.deleteLater()
                    
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
                if status == "Applying":
                    status = "Ready to Apply"
                if status not in self.columns:
                    status = "Analyzed"
                    
                target_layout = self.columns[status]
                
                # Build Card
                from PySide6.QtWidgets import QFrame
                card = QFrame()
                card.setStyleSheet("""
                    QFrame {
                        background-color: #ffffff;
                        border-radius: 10px;
                        border: 1px solid rgba(139, 126, 200, 0.2);
                        padding: 10px;
                    }
                """)
                card_layout = QVBoxLayout(card)
                card_layout.setContentsMargins(10, 10, 10, 10)
                card_layout.setSpacing(6)
                
                title_lbl = QLabel(title)
                title_lbl.setStyleSheet("font-weight: 700; color: #141c29; font-size: 13px; border: none;")
                title_lbl.setWordWrap(True)
                
                s_no = getattr(job, "serial_no", None) or 1
                portal = "Naukri"
                if job.url:
                    u = job.url.lower()
                    if "naukri.com" in u:
                        portal = "Naukri"
                    elif "linkedin.com" in u:
                        portal = "LinkedIn"
                    elif "indeed.com" in u:
                        portal = "Indeed"
                    elif "glassdoor.com" in u:
                        portal = "Glassdoor"
                    elif "foundit" in u or "monster" in u:
                        portal = "Foundit"
                    else:
                        portal = "Portal"
                portal_id = f"{portal}_{s_no}"

                sub_row = QHBoxLayout()
                sub_row.setSpacing(6)
                comp_lbl = QLabel(company)
                comp_lbl.setStyleSheet("color: #5c6479; font-size: 11px; font-weight: 600; border: none;")
                sub_row.addWidget(comp_lbl)

                dot_lbl = QLabel("•")
                dot_lbl.setStyleSheet("color: #8f96a8; font-size: 9px; border: none;")
                sub_row.addWidget(dot_lbl)

                id_badge = QLabel(f"ID #{portal_id}")
                id_badge.setStyleSheet("""
                    background-color: #f4f2fb;
                    color: #5e5298;
                    font-size: 9px;
                    font-family: 'JetBrains Mono', Consolas, monospace;
                    font-weight: 700;
                    padding: 1px 6px;
                    border-radius: 6px;
                    border: 1px solid rgba(139, 126, 200, 0.25);
                """)
                sub_row.addWidget(id_badge)
                sub_row.addStretch()

                score_lbl = QLabel(f"{score_str} Match" if score_str != "N/A" else "Unscored")
                score_lbl.setStyleSheet("""
                    background-color: #e1f5ef;
                    color: #186a59;
                    font-size: 10px;
                    font-weight: 700;
                    font-family: 'JetBrains Mono', Consolas, monospace;
                    padding: 2px 7px;
                    border-radius: 8px;
                    border: 1px solid rgba(24, 106, 89, 0.2);
                """)
                sub_row.addWidget(score_lbl)

                card_layout.addWidget(title_lbl)
                card_layout.addLayout(sub_row)
                
                # Actions based on status
                action_layout = QHBoxLayout()
                action_layout.setSpacing(6)
                
                if job.url:
                    open_btn = QPushButton("Open Link")
                    open_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #e0f2fe;
                            color: #1d4ed8;
                            border: 1px solid rgba(59, 130, 246, 0.25);
                            border-radius: 6px;
                            padding: 4px 8px;
                            font-size: 11px;
                            font-weight: 600;
                        }
                        QPushButton:hover {
                            background-color: #bae6fd;
                        }
                    """)
                    open_btn.clicked.connect(lambda checked=False, u=job.url: self._open_url(u))
                    action_layout.addWidget(open_btn)

                cv_file = os.path.join(os.getcwd(), "outputs", "resumes", f"Vijay_Srivastava_FullStack_{s_no}.pdf")
                if os.path.exists(cv_file):
                    open_cv_btn = QPushButton("Open CV")
                    open_cv_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #f4f2fb;
                            color: #5e5298;
                            border: 1px solid rgba(94, 82, 152, 0.25);
                            border-radius: 6px;
                            padding: 4px 8px;
                            font-size: 11px;
                            font-weight: 600;
                        }
                        QPushButton:hover {
                            background-color: #ddd7f3;
                        }
                    """)
                    open_cv_btn.clicked.connect(lambda checked=False, p=cv_file: QDesktopServices.openUrl(QUrl.fromLocalFile(p)))
                    action_layout.addWidget(open_cv_btn)
                
                if status == "Analyzed":
                    stage_btn = QPushButton("Stage to Apply")
                    stage_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #e8e4f7;
                            color: #5e5298;
                            border: 1px solid rgba(94, 82, 152, 0.25);
                            border-radius: 6px;
                            padding: 4px 8px;
                            font-size: 11px;
                            font-weight: 600;
                        }
                        QPushButton:hover {
                            background-color: #ddd7f3;
                        }
                    """)
                    stage_btn.clicked.connect(lambda checked=False, j=job: self._move_job(j, "Ready to Apply"))
                    action_layout.addWidget(stage_btn)
                    
                    skip_btn = QPushButton("Skip")
                    skip_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #f7f8fc;
                            color: #8f96a8;
                            border: 1px solid rgba(143, 150, 168, 0.3);
                            border-radius: 6px;
                            padding: 4px 8px;
                            font-size: 11px;
                            font-weight: 600;
                        }
                        QPushButton:hover {
                            background-color: #ebedf5;
                            color: #5c6479;
                        }
                    """)
                    skip_btn.clicked.connect(lambda checked=False, j=job: self._move_job(j, "Skipped"))
                    action_layout.addWidget(skip_btn)
                    
                elif status == "Ready to Apply":
                    done_btn = QPushButton("Mark Applied")
                    done_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #e1f5ef;
                            color: #186a59;
                            border: 1px solid rgba(24, 106, 89, 0.25);
                            border-radius: 6px;
                            padding: 4px 8px;
                            font-size: 11px;
                            font-weight: 600;
                        }
                        QPushButton:hover {
                            background-color: #c4ede1;
                        }
                    """)
                    done_btn.clicked.connect(lambda checked=False, j=job: self._move_job(j, "Applied"))
                    action_layout.addWidget(done_btn)

                    skip_btn = QPushButton("Skip")
                    skip_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #f7f8fc;
                            color: #8f96a8;
                            border: 1px solid rgba(143, 150, 168, 0.3);
                            border-radius: 6px;
                            padding: 4px 8px;
                            font-size: 11px;
                            font-weight: 600;
                        }
                        QPushButton:hover {
                            background-color: #ebedf5;
                            color: #5c6479;
                        }
                    """)
                    skip_btn.clicked.connect(lambda checked=False, j=job: self._move_job(j, "Skipped"))
                    action_layout.addWidget(skip_btn)
                
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
