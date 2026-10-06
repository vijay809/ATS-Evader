"""Process Workspace for the human-approved job discovery loop."""
from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QShowEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from openclaw.core.documents import JobDescription
from openclaw.plugins.ats import ATS_ANALYZER_SERVICE, AtsAnalyzer
from openclaw.plugins.browser import BROWSER_SERVICE, BrowserService

if TYPE_CHECKING:
    from openclaw.core.runtime import Runtime
    from openclaw.plugins.semantic_navigator import SemanticNavigator


class JobHuntWorker(QThread):
    job_found = Signal(object) # Will emit ImportedJob
    job_evaluating = Signal(str)
    agent_message = Signal(str)
    error = Signal(str)

    def __init__(self, browser_service: BrowserService, ats_analyzer: AtsAnalyzer, active_resume: str, role: str, location: str, min_exp: int, win_x: int = 0, win_y: int = 0, win_w: int = 1280, win_h: int = 800, threshold: int = 50):
        super().__init__()
        self.setObjectName("JobHuntWorker")
        self.browser = browser_service
        self.analyzer = ats_analyzer
        self.active_resume = active_resume
        self.role = role
        self.location = location
        self.min_exp = min_exp
        self.threshold = threshold
        self.win_x = win_x
        self.win_y = win_y
        self.win_w = win_w
        self.win_h = win_h
        self._skip_current_job = False
        self._stop_requested = False
        self._waiting_for_user = False

    def stop(self) -> None:
        self._stop_requested = True
        self.requestInterruption()

    def move_to_next(self) -> None:
        self._skip_current_job = True
        self._waiting_for_user = False

    def run(self) -> None:
        try:
            asyncio.run(self.do_hunt())
        except Exception as e:
            self.error.emit(str(e))

    async def do_hunt(self) -> None:
        try:
            self.agent_message.emit(f"Launching browser to search for '{self.role}' in '{self.location}'...")
            links = await self.browser.search_naukri_jobs(
                self.role, self.location, max_results=20,
                win_x=self.win_x, win_y=self.win_y, win_w=self.win_w, win_h=self.win_h
            )
            
            if not links:
                self.agent_message.emit("No matching jobs found on the current page.")
                return
                
            self.agent_message.emit(f"Found {len(links)} matching job links. Starting automated review...")
            
            import logging
            logger = logging.getLogger("process_workspace")

            for i, link in enumerate(links):
                if self.isInterruptionRequested() or self._stop_requested:
                    self.agent_message.emit("Job Hunt was stopped by the user.")
                    break
                    
                self._skip_current_job = False

                if not self.browser.page or self.browser.page.is_closed():
                    raise RuntimeError("Browser was closed by the user.")
                    
                self.agent_message.emit(f"[{i+1}/{len(links)}] Fetching job posting...")
                self.job_evaluating.emit(f"Job {i+1}/{len(links)}")

                # Extract JD
                jd_task = asyncio.create_task(self.browser.extract_naukri_jd(link))
                while not jd_task.done():
                    if self.isInterruptionRequested() or self._stop_requested:
                        jd_task.cancel()
                        break
                    if self._skip_current_job:
                        jd_task.cancel()
                        break
                    if not self.browser.page or self.browser.page.is_closed():
                        jd_task.cancel()
                        raise RuntimeError("Browser was closed by the user.")
                    await asyncio.sleep(0.2)

                if self.isInterruptionRequested() or self._stop_requested:
                    self.agent_message.emit("Job Hunt was stopped by the user.")
                    break

                if self._skip_current_job:
                    self._skip_current_job = False
                    self.agent_message.emit(f"⏭ Skipped job [{i+1}/{len(links)}] - moving to next...")
                    continue

                try:
                    jd = jd_task.result()
                except Exception as e:
                    self.agent_message.emit(f"Could not extract posting: {e}")
                    continue

                if not jd or not jd.get('description'):
                    continue
                    
                title = jd.get('title', 'Unknown Title')
                company = jd.get('company', 'Unknown Company')
                if (not company or company == 'Unknown Company') and link:
                    from openclaw.plugins.browser import BrowserService
                    parsed_co = BrowserService._extract_company_from_url(link, title)
                    if parsed_co:
                        company = parsed_co
                
                logger.info(f"Extracting eligibility facts for: {title} at {company}")
                
                # Eligibility facts check
                facts_task = asyncio.create_task(self.analyzer.check_eligibility(jd['description']))
                while not facts_task.done():
                    if self.isInterruptionRequested() or self._stop_requested:
                        facts_task.cancel()
                        break
                    if self._skip_current_job:
                        facts_task.cancel()
                        break
                    if not self.browser.page or self.browser.page.is_closed():
                        facts_task.cancel()
                        raise RuntimeError("Browser was closed by the user.")
                    await asyncio.sleep(0.2)

                if self.isInterruptionRequested() or self._stop_requested:
                    self.agent_message.emit("Job Hunt was stopped by the user.")
                    break

                if self._skip_current_job:
                    self._skip_current_job = False
                    self.agent_message.emit(f"⏭ Stopped evaluating '{title}' - moving to next...")
                    continue

                try:
                    facts = facts_task.result()
                except Exception as e:
                    logger.error(f"Eligibility extraction failed: {e}")
                    facts = None
                    
                if facts:
                    if facts.min_years_experience is not None and facts.min_years_experience > self.min_exp:
                        skip_msg = f"Skipping '{title}' - Requires {facts.min_years_experience} years exp (You have {self.min_exp})."
                        self.agent_message.emit(skip_msg)
                        logger.info(skip_msg)
                        continue
                        
                    if facts.location_type and facts.location_type.lower() != "remote" and self.location.lower() == "remote":
                        skip_msg = f"Skipping '{title}' - It is {facts.location_type} but you require Remote."
                        self.agent_message.emit(skip_msg)
                        logger.info(skip_msg)
                        continue
                        
                self.agent_message.emit(f"[{i+1}/{len(links)}] Scoring: '{title}' at {company}...")
                
                # Poll LLM analysis
                analysis_task = asyncio.create_task(self.analyzer.analyze(self.active_resume, jd['description']))
                while not analysis_task.done():
                    if self.isInterruptionRequested() or self._stop_requested:
                        analysis_task.cancel()
                        break
                    if self._skip_current_job:
                        analysis_task.cancel()
                        break
                    if not self.browser.page or self.browser.page.is_closed():
                        analysis_task.cancel()
                        raise RuntimeError("Browser was closed by the user.")
                    await asyncio.sleep(0.2)

                if self.isInterruptionRequested() or self._stop_requested:
                    self.agent_message.emit("Job Hunt was stopped by the user.")
                    break

                if self._skip_current_job:
                    self._skip_current_job = False
                    self.agent_message.emit(f"⏭ Stopped scoring '{title}' - moving to next...")
                    continue

                try:
                    analysis = analysis_task.result()
                except Exception as e:
                    self.agent_message.emit(f"Analysis failed for '{title}': {e}")
                    continue
                
                unsupported = list(analysis.unsupported_details)
                missing_skills = list(analysis.missing_core_skills)
                formatting = list(analysis.formatting_risks)
                
                status = "Analyzed"
                job_pdf_path: str | None = None
                if analysis.match_score >= self.threshold:
                    msg = f"Score {analysis.match_score}% meets threshold! Tailoring CV..."
                    self.agent_message.emit(msg)
                    logger.info(msg)
                    tailor_task = asyncio.create_task(self.analyzer.tailor(self.active_resume, jd['description']))
                    while not tailor_task.done():
                        if self.isInterruptionRequested() or self._stop_requested:
                            tailor_task.cancel()
                            break
                        if self._skip_current_job:
                            tailor_task.cancel()
                            break
                        if not self.browser.page or self.browser.page.is_closed():
                            tailor_task.cancel()
                            raise RuntimeError("Browser was closed by the user.")
                        await asyncio.sleep(0.2)

                    if self.isInterruptionRequested() or self._stop_requested:
                        self.agent_message.emit("Job Hunt was stopped by the user.")
                        break

                    if self._skip_current_job:
                        self._skip_current_job = False
                        self.agent_message.emit(f"⏭ Stopped tailoring '{title}' - moving to next...")
                        continue

                    try:
                        tailored = tailor_task.result()
                        if tailored.warnings:
                            for w in tailored.warnings:
                                if w not in unsupported:
                                    unsupported.append(w)
                        
                        msg = "CV Tailored! Generating executive PDF..."
                        self.agent_message.emit(msg)
                        logger.info(msg)
                        
                        import uuid
                        from openclaw.core.pdf_gen import PdfGenerator
                        
                        job_id = str(uuid.uuid4())
                        pdf_path = os.path.join(os.getcwd(), "outputs", "resumes", f"cv_{job_id[:8]}.pdf")
                        pdf_path = await PdfGenerator.markdown_to_pdf(tailored.tailored_resume, pdf_path)
                        job_pdf_path = pdf_path
                        
                        msg1 = f"PDF Generated at: {pdf_path}"
                        self.agent_message.emit(msg1)
                        logger.info(msg1)
                        
                        status = "Ready to Apply"
                        msg_ready = f"Match meets threshold ({analysis.match_score}%)! Tailored CV prepared and staged for your review."
                        self.agent_message.emit(msg_ready)
                        logger.info(msg_ready)
                    except Exception as e:
                        self.agent_message.emit(f"Tailoring error: {e}")
                else:
                    msg = f"Skipping '{title}' - Score {analysis.match_score}% is below {self.threshold}% threshold."
                    self.agent_message.emit(msg)
                    logger.info(msg)
                    status = "Skipped"

                # Live Gap & Flag feed alert
                gap_alerts = []
                if missing_skills:
                    gap_alerts.append(f"❌ Missing Core Skills: {', '.join(missing_skills)}")
                if unsupported:
                    gap_alerts.append(f"⚠️ Unsupported Requirements: {'; '.join(unsupported[:2])}")
                if formatting:
                    gap_alerts.append(f"🚩 ATS/Formatting Risks: {'; '.join(formatting[:2])}")

                if gap_alerts:
                    self.agent_message.emit(f"📋 **Gap & Flag Alert for '{title}':**\n" + "\n".join(gap_alerts))
                else:
                    self.agent_message.emit(f"✅ **Gap & Flag Audit:** Zero critical skill gaps or formatting risks detected.")
                
                job = ImportedJob(
                    title,
                    company,
                    jd['description'],
                    link,
                    analysis.match_score,
                    analysis.summary,
                    analysis.recommendations,
                    status=status,
                    pdf_path=job_pdf_path,
                    unsupported_details=unsupported,
                    missing_core_skills=missing_skills,
                    formatting_risks=formatting,
                )
                self.job_found.emit(job)

                # Pause between jobs to allow the user to review the job, cover letter, or CV
                if i + 1 < len(links):
                    self.agent_message.emit(f"📋 **Job [{i+1}/{len(links)}] staged.** Click **'Move to Next Job'** (or **'Stop & Move to Next'**) to evaluate the next posting, or **'Stop Hunt'** to exit.")
                    self._waiting_for_user = True
                    while self._waiting_for_user:
                        if self.isInterruptionRequested() or self._stop_requested:
                            break
                        if self._skip_current_job:
                            self._skip_current_job = False
                            self._waiting_for_user = False
                            break
                        await asyncio.sleep(0.2)

                    if self.isInterruptionRequested() or self._stop_requested:
                        self.agent_message.emit("Job Hunt was stopped by the user.")
                        break
                    
            self.agent_message.emit("Automated search complete. Awaiting further instructions.")
                
        except asyncio.CancelledError:
            self.error.emit("Job hunt was cancelled.")
        except Exception as e:
            self.error.emit(str(e))

class AiChatWorker(QThread):
    agent_message = Signal(str)
    error = Signal(str)

    def __init__(self, navigator: SemanticNavigator, command: str) -> None:
        super().__init__()
        self.setObjectName("AiChatWorker")
        self.navigator = navigator
        self.command = command

    def run(self) -> None:
        try:
            asyncio.run(self.do_chat())
        except Exception as e:
            self.error.emit(str(e))

    async def do_chat(self) -> None:
        try:
            self.agent_message.emit(f"Processing command: '{self.command}'...")

            def stream_callback(msg: str) -> None:
                self.agent_message.emit(msg)

            result = await self.navigator.execute_goal(self.command, max_steps=10, emit_cb=stream_callback)

            if not result.success:
                self.agent_message.emit(f"Execution stopped. {result.error or ''}")

        except Exception as e:
            self.error.emit(str(e))

class DocumentGeneratorWorker(QThread):
    agent_message = Signal(str)
    pdf_ready = Signal(str, str)
    error = Signal(str)

    def __init__(
        self,
        analyzer: AtsAnalyzer,
        active_resume: str,
        job_description: str,
        doc_type: str,
        candidate_name: str = "Applicant",
        company_name: str = "Hiring Team",
    ) -> None:
        super().__init__()
        self.setObjectName("DocumentGeneratorWorker")
        self.analyzer = analyzer
        self.active_resume = active_resume
        self.job_description = job_description
        self.doc_type = doc_type
        self.candidate_name = candidate_name
        self.company_name = company_name

    def run(self) -> None:
        try:
            import asyncio
            import os
            import uuid

            from openclaw.core.pdf_gen import PdfGenerator

            if self.doc_type == "cover_letter":
                self.agent_message.emit("Drafting an executive cover letter based on your master resume and the job description...")
                result = self.analyzer.generate_cover_letter(self.active_resume, self.job_description)

                doc_id = str(uuid.uuid4())[:8]
                out_dir = os.path.join(os.getcwd(), "outputs", "cover_letters")
                os.makedirs(out_dir, exist_ok=True)
                pdf_path = os.path.join(out_dir, f"cover_letter_{doc_id}.pdf")

                asyncio.run(PdfGenerator.cover_letter_to_pdf(
                    result.cover_letter,
                    pdf_path,
                    candidate_name=self.candidate_name,
                    recipient_info=self.company_name,
                ))

                msg = f"📝 **Generated Cover Letter:**\n\n{result.cover_letter}\n\n📄 **Executive PDF Created:** `{pdf_path}`"
                if result.warnings:
                    msg += "\n\n*Warnings: " + ", ".join(result.warnings) + "*"
                self.agent_message.emit(msg)
                self.pdf_ready.emit("cover_letter", pdf_path)

            elif self.doc_type == "tailor_cv":
                self.agent_message.emit("Rewriting and optimizing your CV to match the job description's keywords...")
                tailor_result = self.analyzer.tailor_resume(self.active_resume, self.job_description)

                doc_id = str(uuid.uuid4())[:8]
                out_dir = os.path.join(os.getcwd(), "outputs", "resumes")
                os.makedirs(out_dir, exist_ok=True)
                pdf_path = os.path.join(out_dir, f"cv_{doc_id}.pdf")

                asyncio.run(PdfGenerator.markdown_to_pdf(tailor_result.tailored_resume, pdf_path))

                msg = f"📄 **Tailored CV Generated:**\n\n{tailor_result.tailored_resume}\n\n📄 **Executive PDF Created:** `{pdf_path}`"
                if tailor_result.change_summary:
                    msg += "\n\n*Changes made:*\n- " + "\n- ".join(tailor_result.change_summary)
                if tailor_result.warnings:
                    msg += "\n\n*Warnings: " + ", ".join(tailor_result.warnings) + "*"
                self.agent_message.emit(msg)
                self.pdf_ready.emit("tailor_cv", pdf_path)
        except Exception as e:
            self.error.emit(str(e))


class SidebarMetricWidget(QWidget):
    """Compact telemetry gauge widget for sidebar."""
    def __init__(self, name: str, color: str, track_color: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        name_lbl = QLabel(name)
        name_lbl.setStyleSheet("color: #5c6479; font-size: 10px; font-weight: 600; font-family: 'JetBrains Mono', Consolas, monospace; border: none;")
        self.val_lbl = QLabel("0%")
        self.val_lbl.setStyleSheet(f"color: {color}; font-size: 10px; font-weight: 700; font-family: 'JetBrains Mono', Consolas, monospace; border: none;")
        top_row.addWidget(name_lbl)
        top_row.addStretch()
        top_row.addWidget(self.val_lbl)
        layout.addLayout(top_row)
        
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(4)
        self.bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {track_color};
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 2px;
            }}
        """)
        layout.addWidget(self.bar)

    def set_value(self, val: float) -> None:
        int_val = int(round(val))
        self.val_lbl.setText(f"{int_val}%")
        self.bar.setValue(min(max(int_val, 0), 100))


class ProcessWorkspace(QWidget):
    """The central dashboard for agent interaction and job approvals."""

    def __init__(self, runtime: Runtime) -> None:
        super().__init__()
        self._runtime = runtime
        self._hunt_worker: JobHuntWorker | None = None
        self._doc_workers: list[DocumentGeneratorWorker] = []
        self._browser_workers: list[BrowserLaunchWorker] = []
        self._chat_worker: AiChatWorker | None = None

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # -- LEFT SIDEBAR (Target Profile & Controls) --
        sidebar_scroll = QScrollArea()
        sidebar_scroll.setFixedWidth(320)
        sidebar_scroll.setWidgetResizable(True)
        sidebar_scroll.setStyleSheet("""
            QScrollArea {
                background-color: #f9f9ff;
                border-right: 1px solid rgba(139, 126, 200, 0.2);
                border-top: none;
                border-bottom: none;
                border-left: none;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 5px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #cbd3e6;
                min-height: 20px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background: #8b7ec8;
            }
        """)

        sidebar = QWidget()
        sidebar.setStyleSheet("background-color: transparent;")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(14, 14, 14, 14)
        sidebar_layout.setSpacing(12)
        sidebar_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # 1. Target Profile Header
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(6)

        dot = QLabel("●")
        dot.setStyleSheet("color: #8b7ec8; font-size: 10px; border: none; background: transparent;")
        header_title = QLabel("TARGET PROFILE")
        header_title.setStyleSheet("font-size: 11px; font-weight: 800; color: #141c29; letter-spacing: 0.8px; border: none; background: transparent;")
        header_row.addWidget(dot)
        header_row.addWidget(header_title)
        header_row.addStretch()

        self._config_badge = QLabel("Config #0429")
        self._config_badge.setStyleSheet("""
            color: #8f96a8;
            font-family: 'JetBrains Mono', Consolas, monospace;
            font-size: 10px;
            font-weight: 600;
            background-color: #ffffff;
            padding: 2px 8px;
            border-radius: 10px;
            border: 1px solid rgba(139, 126, 200, 0.25);
        """)
        header_row.addWidget(self._config_badge)
        sidebar_layout.addLayout(header_row)

        # 2. Target Profile Card Form (pastel-card)
        self._profile_card = QFrame()
        self._profile_card.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid rgba(139, 126, 200, 0.22);
                border-radius: 12px;
            }
        """)
        card_layout = QVBoxLayout(self._profile_card)
        card_layout.setContentsMargins(12, 12, 12, 12)
        card_layout.setSpacing(9)

        # Candidate Name Field
        name_box_layout = QVBoxLayout()
        name_box_layout.setSpacing(3)
        name_lbl_title = QLabel("CANDIDATE NAME")
        name_lbl_title.setStyleSheet("color: #8f96a8; font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.6px; border: none;")
        
        name_frame = QFrame()
        name_frame.setStyleSheet("background-color: rgba(244, 242, 251, 0.7); border: 1px solid rgba(139, 126, 200, 0.2); border-radius: 8px;")
        name_frame_layout = QHBoxLayout(name_frame)
        name_frame_layout.setContentsMargins(8, 5, 8, 5)
        name_frame_layout.setSpacing(6)
        
        self._cand_name_val = QLabel("Vijay Kumar Srivastava")
        self._cand_name_val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._cand_name_val.setStyleSheet("color: #141c29; font-size: 12px; font-weight: 700; border: none; background: transparent;")
        
        self._cand_verified_badge = QLabel("Verified")
        self._cand_verified_badge.setStyleSheet("""
            color: #186a59;
            background-color: #e1f5ef;
            border: 1px solid rgba(120, 194, 173, 0.4);
            border-radius: 6px;
            padding: 2px 6px;
            font-size: 9px;
            font-weight: 700;
            font-family: 'JetBrains Mono', Consolas, monospace;
        """)
        name_frame_layout.addWidget(self._cand_name_val, stretch=1)
        name_frame_layout.addWidget(self._cand_verified_badge)
        name_box_layout.addWidget(name_lbl_title)
        name_box_layout.addWidget(name_frame)
        card_layout.addLayout(name_box_layout)

        # Target Role Field
        role_box_layout = QVBoxLayout()
        role_box_layout.setSpacing(3)
        role_lbl_title = QLabel("TARGET ROLE")
        role_lbl_title.setStyleSheet("color: #8f96a8; font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.6px; border: none;")
        
        role_frame = QFrame()
        role_frame.setStyleSheet("background-color: rgba(244, 242, 251, 0.7); border: 1px solid rgba(139, 126, 200, 0.2); border-radius: 8px;")
        role_frame_layout = QHBoxLayout(role_frame)
        role_frame_layout.setContentsMargins(8, 5, 8, 5)
        self._target_role_val = QLabel("Senior Software Engineer")
        self._target_role_val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._target_role_val.setStyleSheet("color: #141c29; font-size: 12px; font-weight: 700; border: none; background: transparent;")
        role_frame_layout.addWidget(self._target_role_val)
        role_box_layout.addWidget(role_lbl_title)
        role_box_layout.addWidget(role_frame)
        card_layout.addLayout(role_box_layout)

        # Location Field
        loc_box_layout = QVBoxLayout()
        loc_box_layout.setSpacing(3)
        loc_lbl_title = QLabel("LOCATION")
        loc_lbl_title.setStyleSheet("color: #8f96a8; font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.6px; border: none;")
        
        loc_frame = QFrame()
        loc_frame.setStyleSheet("background-color: rgba(244, 242, 251, 0.7); border: 1px solid rgba(139, 126, 200, 0.2); border-radius: 8px;")
        loc_frame_layout = QHBoxLayout(loc_frame)
        loc_frame_layout.setContentsMargins(8, 5, 8, 5)
        loc_frame_layout.setSpacing(6)
        loc_pin = QLabel("📍")
        loc_pin.setStyleSheet("font-size: 11px; border: none; background: transparent;")
        self._location_val = QLabel("Noida, Uttar Pradesh")
        self._location_val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._location_val.setStyleSheet("color: #141c29; font-size: 12px; font-weight: 600; border: none; background: transparent;")
        loc_frame_layout.addWidget(loc_pin)
        loc_frame_layout.addWidget(self._location_val, stretch=1)
        loc_box_layout.addWidget(loc_lbl_title)
        loc_box_layout.addWidget(loc_frame)
        card_layout.addLayout(loc_box_layout)

        # Experience & Work Mode (2 columns)
        exp_mode_layout = QHBoxLayout()
        exp_mode_layout.setSpacing(8)

        exp_box = QVBoxLayout()
        exp_box.setSpacing(3)
        exp_lbl_title = QLabel("MIN EXPERIENCE")
        exp_lbl_title.setStyleSheet("color: #8f96a8; font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.6px; border: none;")
        exp_frame = QFrame()
        exp_frame.setStyleSheet("background-color: rgba(244, 242, 251, 0.7); border: 1px solid rgba(139, 126, 200, 0.2); border-radius: 8px;")
        exp_frame_layout = QHBoxLayout(exp_frame)
        exp_frame_layout.setContentsMargins(8, 5, 8, 5)
        self._exp_val = QLabel("5+ Years")
        self._exp_val.setStyleSheet("color: #141c29; font-size: 12px; font-weight: 700; border: none; background: transparent;")
        exp_frame_layout.addWidget(self._exp_val)
        exp_box.addWidget(exp_lbl_title)
        exp_box.addWidget(exp_frame)

        mode_box = QVBoxLayout()
        mode_box.setSpacing(3)
        mode_lbl_title = QLabel("WORK MODE")
        mode_lbl_title.setStyleSheet("color: #8f96a8; font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.6px; border: none;")
        mode_frame = QFrame()
        mode_frame.setStyleSheet("background-color: rgba(244, 242, 251, 0.7); border: 1px solid rgba(139, 126, 200, 0.2); border-radius: 8px;")
        mode_frame_layout = QHBoxLayout(mode_frame)
        mode_frame_layout.setContentsMargins(8, 5, 8, 5)
        self._mode_val = QLabel("Hybrid / Remote")
        self._mode_val.setStyleSheet("color: #141c29; font-size: 12px; font-weight: 700; border: none; background: transparent;")
        mode_frame_layout.addWidget(self._mode_val)
        mode_box.addWidget(mode_lbl_title)
        mode_box.addWidget(mode_frame)

        exp_mode_layout.addLayout(exp_box, 1)
        exp_mode_layout.addLayout(mode_box, 1)
        card_layout.addLayout(exp_mode_layout)

        # Dynamic extra prefs area
        self._extra_prefs_container = QWidget()
        self._extra_prefs_container.setStyleSheet("background: transparent; border: none;")
        self._extra_prefs_layout = QVBoxLayout(self._extra_prefs_container)
        self._extra_prefs_layout.setContentsMargins(0, 0, 0, 0)
        self._extra_prefs_layout.setSpacing(6)
        card_layout.addWidget(self._extra_prefs_container)

        # ATS Match Threshold (integrated in card)
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: rgba(139, 126, 200, 0.15); max-height: 1px; border: none;")
        card_layout.addWidget(sep)

        thresh_header = QHBoxLayout()
        thresh_title = QLabel("ATS MATCH THRESHOLD")
        thresh_title.setStyleSheet("color: #8f96a8; font-size: 9px; font-weight: 800; letter-spacing: 0.6px; border: none;")
        self._threshold_pct_badge = QLabel("50%")
        self._threshold_pct_badge.setStyleSheet("""
            color: #5e5298;
            background-color: #e8e4f7;
            border: 1px solid rgba(139, 126, 200, 0.35);
            border-radius: 10px;
            padding: 2px 8px;
            font-size: 11px;
            font-weight: 700;
            font-family: 'JetBrains Mono', Consolas, monospace;
        """)
        thresh_header.addWidget(thresh_title)
        thresh_header.addStretch()
        thresh_header.addWidget(self._threshold_pct_badge)
        card_layout.addLayout(thresh_header)

        self._threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self._threshold_slider.setRange(10, 95)
        self._threshold_slider.setSingleStep(5)
        self._threshold_slider.setPageStep(5)
        self._threshold_slider.setValue(50)
        self._threshold_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 6px;
                background: #e8e4f7;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #8b7ec8;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #5e5298;
                border: 2px solid #ffffff;
                width: 16px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 8px;
            }
            QSlider::handle:horizontal:hover {
                background: #493c81;
            }
        """)
        self._threshold_slider.valueChanged.connect(
            lambda v: self._threshold_pct_badge.setText(f"{v}%")
        )
        card_layout.addWidget(self._threshold_slider)

        tick_lbl = QLabel("|    |    |    |    |    |    |    |    |    |")
        tick_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tick_lbl.setStyleSheet("color: #8f96a8; font-size: 7px; font-family: 'JetBrains Mono', Consolas, monospace; border: none; padding: 0;")
        card_layout.addWidget(tick_lbl)

        sidebar_layout.addWidget(self._profile_card)

        # 3. Hunting Execution Action Buttons
        exec_layout = QVBoxLayout()
        exec_layout.setSpacing(7)

        self._toggle_btn = QPushButton("Start Job Hunt")
        self._toggle_btn.setMinimumHeight(40)
        self._toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: #8b7ec8; color: #ffffff;
                border-radius: 11px; font-size: 11px; font-weight: 800;
                letter-spacing: 0.8px; text-transform: uppercase;
                border: none;
            }
            QPushButton:hover { background-color: #5e5298; }
            QPushButton:disabled { background-color: #e8e4f7; color: #8f96a8; }
        """)
        self._toggle_btn.clicked.connect(self.toggle_job_hunt)
        exec_layout.addWidget(self._toggle_btn)

        self._next_btn = QPushButton("⏭ Move to Next Job")
        self._next_btn.setMinimumHeight(40)
        self._next_btn.setStyleSheet("""
            QPushButton {
                background-color: #fbbd9e; color: #5e2b10;
                border: 1px solid rgba(194, 94, 54, 0.3);
                border-radius: 11px; font-size: 11px; font-weight: 800;
                letter-spacing: 0.8px; text-transform: uppercase;
            }
            QPushButton:hover { background-color: #f8ad8a; }
            QPushButton:disabled { background-color: #fff0e8; color: #8f96a8; border: 1px solid rgba(194, 94, 54, 0.15); }
        """)
        self._next_btn.setEnabled(False)
        self._next_btn.clicked.connect(self.move_to_next_job)
        exec_layout.addWidget(self._next_btn)

        sec_grid = QHBoxLayout()
        sec_grid.setSpacing(7)

        self._reset_btn = QPushButton("🔄 Reset Browser")
        self._reset_btn.setMinimumHeight(34)
        self._reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffffff; color: #5c6479;
                border: 1px solid rgba(139, 126, 200, 0.25); border-radius: 10px;
                font-size: 11px; font-weight: 600;
            }
            QPushButton:hover { background-color: #f4f2fb; color: #5e5298; border-color: rgba(139, 126, 200, 0.4); }
        """)
        self._reset_btn.clicked.connect(self._reset_browser)

        self._folder_btn = QPushButton("📁 Outputs")
        self._folder_btn.setMinimumHeight(34)
        self._folder_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffffff; color: #5c6479;
                border: 1px solid rgba(139, 126, 200, 0.25); border-radius: 10px;
                font-size: 11px; font-weight: 600;
            }
            QPushButton:hover { background-color: #f4f2fb; color: #5e5298; border-color: rgba(139, 126, 200, 0.4); }
        """)
        self._folder_btn.clicked.connect(self._open_outputs_folder)

        sec_grid.addWidget(self._reset_btn, 1)
        sec_grid.addWidget(self._folder_btn, 1)
        exec_layout.addLayout(sec_grid)
        sidebar_layout.addLayout(exec_layout)

        # 4. Hardware Telemetry Card
        telemetry_card = QFrame()
        telemetry_card.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid rgba(139, 126, 200, 0.2);
                border-radius: 11px;
            }
        """)
        telem_layout = QVBoxLayout(telemetry_card)
        telem_layout.setContentsMargins(10, 8, 10, 8)
        telem_layout.setSpacing(6)

        telem_header = QHBoxLayout()
        telem_header.setContentsMargins(0, 0, 0, 0)
        telem_dot = QLabel("●")
        telem_dot.setStyleSheet("color: #78c2ad; font-size: 9px; border: none; background: transparent;")
        telem_title = QLabel("HARDWARE TELEMETRY")
        telem_title.setStyleSheet("color: #5c6479; font-size: 9px; font-weight: 700; font-family: 'JetBrains Mono', Consolas, monospace; border: none; background: transparent;")
        telem_header.addWidget(telem_dot)
        telem_header.addWidget(telem_title)
        telem_header.addStretch()

        self._telemetry_spec_lbl = QLabel("Local AI Engine")
        self._telemetry_spec_lbl.setStyleSheet("color: #8f96a8; font-size: 9px; font-family: 'JetBrains Mono', Consolas, monospace; border: none; background: transparent;")
        telem_header.addWidget(self._telemetry_spec_lbl)
        telem_layout.addLayout(telem_header)

        # 2x2 Grid of Gauges
        telem_grid = QGridLayout()
        telem_grid.setContentsMargins(0, 0, 0, 0)
        telem_grid.setHorizontalSpacing(10)
        telem_grid.setVerticalSpacing(4)

        self._side_cpu = SidebarMetricWidget("CPU", color="#3b82f6", track_color="#e0f2fe")
        self._side_ram = SidebarMetricWidget("RAM", color="#c25e36", track_color="#fff0e8")
        self._side_gpu = SidebarMetricWidget("GPU", color="#186a59", track_color="#e1f5ef")
        self._side_vram = SidebarMetricWidget("VRAM", color="#8e4555", track_color="#ffdad6")

        telem_grid.addWidget(self._side_cpu, 0, 0)
        telem_grid.addWidget(self._side_ram, 0, 1)
        telem_grid.addWidget(self._side_gpu, 1, 0)
        telem_grid.addWidget(self._side_vram, 1, 1)
        telem_layout.addLayout(telem_grid)

        sidebar_layout.addWidget(telemetry_card)
        sidebar_layout.addStretch()

        sidebar_scroll.setWidget(sidebar)

        # -- RIGHT MAIN AREA (Chat/Feed) --
        main_area = QWidget()
        main_area.setStyleSheet("background-color: #f7f8fc;")
        main_area_layout = QVBoxLayout(main_area)
        main_area_layout.setContentsMargins(20, 20, 20, 20)
        main_area_layout.setSpacing(12)
        
        # Scrollable feed
        feed_scroll = QScrollArea()
        feed_scroll.setWidgetResizable(True)
        feed_scroll.setStyleSheet("""
            QScrollArea {
                border: none; background: transparent;
            }
            QScrollBar:vertical {
                background: #edf1fa;
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: #cbd3e6;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background: #aab4cc;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        
        self._feed_widget = QWidget()
        self._feed_widget.setStyleSheet("background: transparent;")
        self._feed_layout = QVBoxLayout(self._feed_widget)
        self._feed_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._feed_layout.setSpacing(12)
        feed_scroll.setWidget(self._feed_widget)
        
        main_area_layout.addWidget(feed_scroll, stretch=1)

        # Chat Input Container (Pastel Card with Send Pill)
        chat_frame = QFrame()
        chat_frame.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid rgba(139, 126, 200, 0.25);
                border-radius: 24px;
            }
        """)
        chat_layout = QHBoxLayout(chat_frame)
        chat_layout.setContentsMargins(12, 4, 6, 4)
        chat_layout.setSpacing(8)

        chat_icon = QLabel("💬")
        chat_icon.setStyleSheet("font-size: 14px; border: none; background: transparent;")
        chat_layout.addWidget(chat_icon)

        self._chat_input = QLineEdit()
        self._chat_input.setPlaceholderText("Chat with AI to guide the job hunt or ask questions...")
        self._chat_input.setMinimumHeight(38)
        self._chat_input.setStyleSheet("""
            QLineEdit {
                background: transparent; color: #141c29; border: none;
                font-size: 13px; padding: 0 4px;
            }
        """)
        
        send_btn = QPushButton("Send")
        send_btn.setFixedHeight(36)
        send_btn.setStyleSheet("""
            QPushButton {
                background-color: #5e5298; color: #ffffff;
                font-weight: bold; border: none; border-radius: 18px;
                padding: 0 18px; font-size: 12px;
            }
            QPushButton:hover { background-color: #493c81; }
        """)
        
        chat_layout.addWidget(self._chat_input, stretch=1)
        chat_layout.addWidget(send_btn)
        send_btn.clicked.connect(self.send_chat_message)
        self._chat_input.returnPressed.connect(self.send_chat_message)
        main_area_layout.addWidget(chat_frame)

        # Add to splitter
        splitter.addWidget(sidebar_scroll)
        splitter.addWidget(main_area)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        main_layout.addWidget(splitter)
        self.refresh_preferences()
        self._add_notice("Click 'Start Job Hunt' to let the agent auto-search based on your Target Profile. Chat with me below to guide the process (e.g. 'Apply to this one').")

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.refresh_preferences()

    def update_telemetry(self, cpu: float, ram: float, gpu: float, vram: float) -> None:
        """Update hardware telemetry gauges in the sidebar."""
        self._side_cpu.set_value(cpu)
        self._side_ram.set_value(ram)
        self._side_gpu.set_value(gpu)
        self._side_vram.set_value(vram)

    def set_telemetry_model(self, model_name: str) -> None:
        """Update the telemetry model label in the sidebar."""
        clean_name = model_name.removesuffix(":latest")
        if len(clean_name) > 18:
            clean_name = clean_name[:16] + ".."
        self._telemetry_spec_lbl.setText(clean_name)

    def refresh_preferences(self) -> None:
        """Load preferences from SQLite and display them in the unified Target Profile card."""
        # Clear extra dynamic prefs
        while self._extra_prefs_layout.count():
            child = self._extra_prefs_layout.takeAt(0)
            if child is not None:
                widget = child.widget()
                if widget is not None:
                    widget.setParent(None)
                    widget.deleteLater()

        try:
            import json
            active_resume = self._runtime.plugins._context.documents.get_active_structured_resume()
            if not active_resume:
                self._cand_name_val.setText("No Active Profile")
                self._cand_verified_badge.setText("Unset")
                self._cand_verified_badge.setStyleSheet("color: #8e4555; background-color: #ffdad6; border: 1px solid rgba(142, 69, 85, 0.4); border-radius: 6px; padding: 2px 6px; font-size: 9px; font-weight: 700; font-family: 'JetBrains Mono', Consolas, monospace;")
                self._target_role_val.setText("Set up profile in Setup tab")
                self._location_val.setText("Remote")
                self._exp_val.setText("0+ Years")
                self._mode_val.setText("Remote")
                self._config_badge.setText("Config #0000")
                return

            parsed = json.loads(active_resume.parsed_json)
            if isinstance(parsed, dict) and "preferences" in parsed:
                prefs = parsed["preferences"]
            else:
                prefs = {p.key: p.value for p in self._runtime.plugins._context.documents.get_preferences()}

            cand_name = prefs.get("Candidate Name", active_resume.name or "Vijay Kumar Srivastava")
            target_role = prefs.get("Target Role", "Senior Software Engineer")
            location = prefs.get("Location", "Noida, Uttar Pradesh")
            min_exp = prefs.get("Min Years Exp", "5+ Years")
            work_mode = prefs.get("Work Mode", "Hybrid / Remote")

            self._cand_name_val.setText(cand_name)
            self._cand_verified_badge.setText("Verified")
            self._cand_verified_badge.setStyleSheet("""
                color: #186a59;
                background-color: #e1f5ef;
                border: 1px solid rgba(120, 194, 173, 0.4);
                border-radius: 6px;
                padding: 2px 6px;
                font-size: 9px;
                font-weight: 700;
                font-family: 'JetBrains Mono', Consolas, monospace;
            """)

            self._target_role_val.setText(target_role)
            self._location_val.setText(location)
            self._exp_val.setText(min_exp if ("Year" in min_exp or "+" in min_exp) else f"{min_exp} Years")
            self._mode_val.setText(work_mode)
            self._config_badge.setText(f"Config #{str(active_resume.id)[:4]}")

            # Display any other additional preferences (e.g. Target Salary, Primary Skills)
            known_keys = {"Candidate Name", "Target Role", "Location", "Min Years Exp", "Work Mode"}
            extra_keys = [k for k in prefs.keys() if k not in known_keys]
            for k in extra_keys[:3]: # Keep compact
                v = prefs[k]
                extra_box = QVBoxLayout()
                extra_box.setSpacing(2)
                extra_lbl = QLabel(k.upper())
                extra_lbl.setStyleSheet("color: #8f96a8; font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.6px; border: none;")
                extra_frame = QFrame()
                extra_frame.setStyleSheet("background-color: rgba(244, 242, 251, 0.7); border: 1px solid rgba(139, 126, 200, 0.2); border-radius: 8px;")
                extra_flayout = QHBoxLayout(extra_frame)
                extra_flayout.setContentsMargins(8, 4, 8, 4)
                extra_val = QLabel(v)
                extra_val.setStyleSheet("color: #141c29; font-size: 11px; font-weight: 600; border: none; background: transparent;")
                extra_flayout.addWidget(extra_val)
                extra_box.addWidget(extra_lbl)
                extra_box.addWidget(extra_frame)
                
                holder = QWidget()
                holder.setStyleSheet("background: transparent; border: none;")
                holder.setLayout(extra_box)
                self._extra_prefs_layout.addWidget(holder)

        except (AttributeError, LookupError, json.JSONDecodeError):
            return

    def _reset_browser(self) -> None:
        try:
            browser = self._runtime.services.get(BROWSER_SERVICE)
            if isinstance(browser, BrowserService):
                browser.reset_session()
                self._add_notice("Browser session and cookies have been wiped. The next launch will be a fresh login.")
        except LookupError:
            self._add_notice("Browser capability is unavailable.")

    def _open_outputs_folder(self) -> None:
        outputs_dir = os.path.join(os.getcwd(), "outputs")
        os.makedirs(outputs_dir, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(outputs_dir))

    def add_user_message(self, text: str) -> None:
        msg = QLabel(text)
        msg.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        msg.setWordWrap(True)
        msg.setStyleSheet("""
            color: #141c29;
            background-color: #e8e4f7;
            border: 1px solid rgba(139, 126, 200, 0.3);
            border-radius: 12px;
            padding: 10px 14px;
            margin-left: 60px;
            font-size: 13px;
        """)
        self._feed_layout.addWidget(msg)

    def add_agent_message(self, text: str) -> None:
        msg = QLabel(text)
        msg.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        msg.setWordWrap(True)
        if any(text.startswith(p) for p in ("📋", "✅", "🤖", "📁", "🎯", "⚡", "📄", "⏭")):
            msg.setStyleSheet("""
                color: #2b3345;
                background-color: #ffffff;
                border: 1px solid rgba(139, 126, 200, 0.22);
                border-left: 4px solid #8b7ec8;
                border-radius: 8px;
                padding: 9px 12px;
                font-size: 12px;
            """)
        else:
            msg.setStyleSheet("""
                color: #484550;
                background-color: rgba(244, 242, 251, 0.85);
                border: 1px solid rgba(139, 126, 200, 0.15);
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 12px;
            """)
        self._feed_layout.addWidget(msg)

    def send_chat_message(self) -> None:
        text = self._chat_input.text().strip()
        if not text:
            return

        self._chat_input.clear()
        self.add_user_message(text)

        lowered = text.lower()
        if lowered in ("next", "next job", "move to next", "skip to next", "skip"):
            if self._hunt_worker and self._hunt_worker.isRunning():
                self.move_to_next_job()
                return
        if lowered in ("stop", "stop hunt", "cancel", "halt"):
            if self._hunt_worker and self._hunt_worker.isRunning():
                self.stop_job_hunt()
                return

        try:
            from openclaw.plugins.semantic_navigator import SemanticNavigator
            nav_service = self._runtime.services.get("browser.navigator")
            if not isinstance(nav_service, SemanticNavigator):
                self.add_agent_message("Browser navigator is unavailable.")
                return
        except LookupError:
            self.add_agent_message("Browser capability is unavailable.")
            return

        self._chat_input.setEnabled(False)
        self._chat_worker = AiChatWorker(nav_service, text)
        self._chat_worker.agent_message.connect(self.add_agent_message)
        self._chat_worker.error.connect(lambda e: self.add_agent_message(f"Error: {e}"))
        self._chat_worker.finished.connect(lambda: self._chat_input.setEnabled(True))
        self._chat_worker.start()

    def add_job_card(
        self,
        title: str,
        company: str,
        match_score: int,
        analysis: list[str],
        job_id: str,
        pdf_path: str | None = None,
        unsupported_details: list[str] | None = None,
        missing_core_skills: list[str] | None = None,
        formatting_risks: list[str] | None = None,
    ) -> None:
        """Adds a job match card to the feed."""
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid rgba(139, 126, 200, 0.22);
                border-radius: 14px;
                padding: 16px;
            }
        """)
        layout = QVBoxLayout(card)
        layout.setSpacing(10)
        layout.setContentsMargins(14, 14, 14, 14)
        
        # Header
        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)
        
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title_lbl = QLabel(title)
        title_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet("font-size: 16px; font-weight: 700; color: #141c29; border: none;")
        
        company_lbl = QLabel(company)
        company_lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #5c6479; border: none;")
        title_box.addWidget(title_lbl)
        title_box.addWidget(company_lbl)
        
        score_lbl = QLabel(f"{match_score}% Match")
        score_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        score_lbl.setStyleSheet("""
            background-color: #fff0e8;
            color: #c25e36;
            font-size: 13px;
            font-weight: 700;
            padding: 5px 12px;
            border-radius: 12px;
            border: 1px solid rgba(194, 94, 54, 0.25);
        """)
        
        header_layout.addLayout(title_box, 1)
        header_layout.addWidget(score_lbl, 0)
        layout.addLayout(header_layout)

        # Analysis Summary
        if analysis:
            summary_box = QVBoxLayout()
            summary_box.setSpacing(4)
            for point in analysis:
                p_lbl = QLabel(f"• {point}")
                p_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                p_lbl.setWordWrap(True)
                p_lbl.setStyleSheet("color: #5c6479; font-size: 13px; border: none; line-height: 1.4;")
                summary_box.addWidget(p_lbl)
            layout.addLayout(summary_box)

        # Gap & Flag Report
        has_gaps = bool(missing_core_skills or unsupported_details or formatting_risks)
        if has_gaps:
            gap_frame = QFrame()
            gap_frame.setStyleSheet("""
                QFrame {
                    background-color: #fff5f0;
                    border: 1px solid rgba(194, 94, 54, 0.25);
                    border-radius: 10px;
                    padding: 8px;
                    margin-top: 4px;
                    margin-bottom: 4px;
                }
            """)
            gap_layout = QVBoxLayout(gap_frame)
            gap_layout.setContentsMargins(10, 8, 10, 8)
            gap_layout.setSpacing(6)

            gap_header = QLabel("⚠️ GAP & FLAG AUDIT REPORT")
            gap_header.setStyleSheet("color: #c25e36; font-size: 11px; font-weight: 800; border: none; letter-spacing: 0.6px;")
            gap_layout.addWidget(gap_header)

            if missing_core_skills:
                skills_str = ", ".join(missing_core_skills)
                skills_lbl = QLabel(f"❌ <b>Missing Core Skills:</b> <span style='color: #8e4555; font-weight: 600;'>{skills_str}</span>")
                skills_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                skills_lbl.setWordWrap(True)
                skills_lbl.setStyleSheet("color: #591b28; font-size: 12px; border: none;")
                gap_layout.addWidget(skills_lbl)

            if unsupported_details:
                for item in unsupported_details:
                    unsup_lbl = QLabel(f"⚠️ <b>Unsupported Requirement:</b> {item}")
                    unsup_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                    unsup_lbl.setWordWrap(True)
                    unsup_lbl.setStyleSheet("color: #5e2b10; font-size: 12px; border: none;")
                    gap_layout.addWidget(unsup_lbl)

            if formatting_risks:
                for item in formatting_risks:
                    risk_lbl = QLabel(f"🚩 <b>ATS / Formatting Risk:</b> {item}")
                    risk_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                    risk_lbl.setWordWrap(True)
                    risk_lbl.setStyleSheet("color: #493c81; font-size: 12px; border: none;")
                    gap_layout.addWidget(risk_lbl)

            layout.addWidget(gap_frame)
        else:
            clean_badge = QLabel("✓ Zero Critical Gaps or Formatting Risks Detected")
            clean_badge.setStyleSheet("""
                background-color: #e1f5ef;
                color: #186a59;
                font-size: 12px;
                font-weight: 600;
                padding: 6px 12px;
                border-radius: 8px;
                border: 1px solid rgba(24, 106, 89, 0.2);
            """)
            layout.addWidget(clean_badge)

        # Actions
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(8)

        approve_btn = QPushButton("Review in Browser")
        approve_btn.setMinimumHeight(36)
        approve_btn.setStyleSheet("""
            QPushButton {
                background-color: #e0f2fe;
                color: #1d4ed8;
                border: 1px solid rgba(59, 130, 246, 0.3);
                border-radius: 8px;
                font-weight: 600;
                font-size: 12px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #bae6fd;
            }
        """)
        
        applied_btn = QPushButton("Mark Applied")
        applied_btn.setMinimumHeight(36)
        applied_btn.setStyleSheet("""
            QPushButton {
                background-color: #e1f5ef;
                color: #186a59;
                border: 1px solid rgba(24, 106, 89, 0.3);
                border-radius: 8px;
                font-weight: 600;
                font-size: 12px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #c4ede1;
            }
        """)

        cover_letter_btn = QPushButton("Cover Letter")
        cover_letter_btn.setMinimumHeight(36)
        cover_letter_btn.setStyleSheet("""
            QPushButton {
                background-color: #f4f2fb;
                color: #493c81;
                border: 1px solid rgba(94, 82, 152, 0.25);
                border-radius: 8px;
                font-weight: 600;
                font-size: 12px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #e8e4f7;
            }
        """)
        
        tailor_cv_btn = QPushButton("Tailor CV")
        tailor_cv_btn.setMinimumHeight(36)
        tailor_cv_btn.setStyleSheet("""
            QPushButton {
                background-color: #e1f5ef;
                color: #186a59;
                border: 1px solid rgba(24, 106, 89, 0.25);
                border-radius: 8px;
                font-weight: 600;
                font-size: 12px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #c4ede1;
            }
        """)
        
        skip_btn = QPushButton("Skip")
        skip_btn.setMinimumHeight(36)
        skip_btn.setStyleSheet("""
            QPushButton {
                background-color: #f7f8fc;
                color: #8f96a8;
                border: 1px solid rgba(143, 150, 168, 0.3);
                border-radius: 8px;
                font-weight: 600;
                font-size: 12px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #ebedf5;
                color: #5c6479;
            }
        """)

        def handle_skip() -> None:
            job = self._runtime.plugins._context.documents.get_job_description(job_id)
            if job:
                job.status = "Skipped"
                self._runtime.plugins._context.documents.save_job_description(job)
            card.deleteLater()
            
        def handle_applied() -> None:
            job = self._runtime.plugins._context.documents.get_job_description(job_id)
            if job:
                job.status = "Applied"
                self._runtime.plugins._context.documents.save_job_description(job)
            applied_btn.setEnabled(False)
            applied_btn.setText("✓ Applied")
            applied_btn.setStyleSheet("background-color: #a3eed8; color: #186a59; border: 1px solid #78c2ad; border-radius: 8px; font-weight: 700; font-size: 12px;")
            self.add_agent_message(f"Marked '{title}' at {company} as Applied.")

        approve_btn.clicked.connect(lambda: self._open_for_review(job_id))
        applied_btn.clicked.connect(handle_applied)
        skip_btn.clicked.connect(handle_skip)
        
        cover_letter_btn.clicked.connect(lambda: self._generate_document("cover_letter", job_id))
        tailor_cv_btn.clicked.connect(lambda: self._generate_document("tailor_cv", job_id))
        
        actions_layout.addWidget(approve_btn)
        actions_layout.addWidget(applied_btn)

        if pdf_path and os.path.exists(pdf_path):
            open_cv_btn = QPushButton("Open Tailored CV")
            open_cv_btn.setMinimumHeight(36)
            open_cv_btn.setStyleSheet("""
                QPushButton {
                    background-color: #e8e4f7;
                    color: #5e5298;
                    border: 1px solid rgba(94, 82, 152, 0.3);
                    border-radius: 8px;
                    font-weight: 600;
                    font-size: 12px;
                    padding: 6px 12px;
                }
                QPushButton:hover {
                    background-color: #ddd7f3;
                }
            """)
            open_cv_btn.clicked.connect(lambda checked=False, p=pdf_path: QDesktopServices.openUrl(QUrl.fromLocalFile(p)))
            actions_layout.addWidget(open_cv_btn)

        actions_layout.addWidget(cover_letter_btn)
        actions_layout.addWidget(tailor_cv_btn)

        next_job_btn = QPushButton("⏭ Move to Next")
        next_job_btn.setMinimumHeight(36)
        next_job_btn.setStyleSheet("""
            QPushButton {
                background-color: #fff0e8; 
                color: #c25e36; 
                border: 1px solid rgba(194, 94, 54, 0.35); 
                border-radius: 8px; 
                font-weight: 600;
                font-size: 12px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #ffe0d0;
            }
        """)
        next_job_btn.clicked.connect(self.move_to_next_job)
        actions_layout.addWidget(next_job_btn)

        actions_layout.addWidget(skip_btn)
        layout.addLayout(actions_layout)

        self._feed_layout.addWidget(card)

    def _generate_document(self, doc_type: str, job_id: str) -> None:
        try:
            analyzer = self._runtime.services.get(ATS_ANALYZER_SERVICE)
            active_resume = self._runtime.plugins._context.documents.get_active_structured_resume()
            if not active_resume or not isinstance(analyzer, AtsAnalyzer):
                self._add_notice("Analyzer or Resume missing.")
                return
                
            job = self._runtime.plugins._context.documents.get_job_description(job_id)
            if not job:
                self._add_notice("Job data missing.")
                return
                
            candidate_name = "Applicant"
            try:
                import json
                parsed = json.loads(active_resume.parsed_json)
                if isinstance(parsed, dict) and "preferences" in parsed:
                    candidate_name = parsed["preferences"].get("Candidate Name", "Applicant")
            except Exception:
                pass

            company_name = "Hiring Team"
            if " at " in job.name:
                company_name = job.name.split(" at ", 1)[1]

            worker = DocumentGeneratorWorker(
                analyzer,
                active_resume.raw_content,
                job.content,
                doc_type,
                candidate_name=candidate_name,
                company_name=company_name,
            )
            self._doc_workers.append(worker)
            worker.agent_message.connect(self.add_agent_message)
            worker.pdf_ready.connect(self._on_pdf_ready)
            worker.error.connect(self._on_worker_failed)
            worker.finished.connect(lambda w=worker: self._cleanup_doc_worker(w))
            worker.start()
        except Exception as e:
            self._on_worker_failed(str(e))

    def _cleanup_doc_worker(self, worker: DocumentGeneratorWorker) -> None:
        if worker in self._doc_workers:
            self._doc_workers.remove(worker)
        worker.deleteLater()

    def _cleanup_browser_worker(self, worker: BrowserLaunchWorker) -> None:
        if worker in self._browser_workers:
            self._browser_workers.remove(worker)
        worker.deleteLater()

    def _on_pdf_ready(self, doc_type: str, pdf_path: str) -> None:
        if os.path.exists(pdf_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(pdf_path))

    def start_job_hunt(self) -> None:
        """Automated Job Hunt: searches Naukri, extracts JDs, and scores them locally."""
        try:
            import json
            active_resume = self._runtime.plugins._context.documents.get_active_structured_resume()
            if not active_resume:
                QMessageBox.warning(self, "No Profile", "Please set an Active Profile in the Setup tab first.")
                return
                
            parsed = json.loads(active_resume.parsed_json)
            if isinstance(parsed, dict) and "preferences" in parsed:
                prefs = parsed["preferences"]
            else:
                prefs = {p.key: p.value for p in self._runtime.plugins._context.documents.get_preferences()}
                
            role = prefs.get("Target Role", "Software Engineer")
            location = prefs.get("Location", "Remote")
            min_exp_str = prefs.get("Min Years Exp", "0")
            try:
                min_exp = int(min_exp_str.split()[0])
            except (ValueError, IndexError):
                min_exp = 0
            
            browser = self._runtime.services.get(BROWSER_SERVICE)
            analyzer = self._runtime.services.get(ATS_ANALYZER_SERVICE)
            
            if not isinstance(browser, BrowserService) or not isinstance(analyzer, AtsAnalyzer):
                self._add_notice("Browser or ATS capability is not configured correctly.")
                return
                
            if self._hunt_worker and self._hunt_worker.isRunning():
                self.add_agent_message("Job hunt is already in progress.")
                return

            # Resize app to left 50% and put browser on right 50%
            from PySide6.QtGui import QGuiApplication
            screen = QGuiApplication.primaryScreen()
            avail_geo = screen.availableGeometry()
            w = avail_geo.width() // 2
            
            # Pad Y by 40px and reduce height by 40px so the Windows title bar fits
            y_pad = 40
            h = avail_geo.height() - y_pad
            y_pos = avail_geo.y() + y_pad
            
            self.window().setGeometry(avail_geo.x(), y_pos, w, h)

            self._toggle_btn.setText("⏹ Stop Hunt Execution")
            self._toggle_btn.setStyleSheet("""
                QPushButton {
                    background-color: #f4a8b8;
                    color: #591b28;
                    border: 1px solid rgba(142, 69, 85, 0.25);
                    border-radius: 11px;
                    font-size: 11px;
                    font-weight: 800;
                    letter-spacing: 0.8px;
                    text-transform: uppercase;
                    padding: 10px 0;
                }
                QPushButton:hover { background-color: #ee95a8; }
                QPushButton:disabled { background-color: #f7f8fc; color: #8f96a8; }
            """)
            self._next_btn.setEnabled(True)
            self._next_btn.setText("⏭ Move to Next Job")
            self.add_agent_message(f"Beginning automated job hunt for '{role}' in '{location}'...")
            
            threshold = self._threshold_slider.value()
            self._hunt_worker = JobHuntWorker(
                browser, analyzer, active_resume.raw_content, role, location, min_exp,
                win_x=avail_geo.x() + w, win_y=y_pos, win_w=w, win_h=h, threshold=threshold
            )
            self._hunt_worker.agent_message.connect(self.add_agent_message)
            self._hunt_worker.job_evaluating.connect(self._on_job_evaluating)
            self._hunt_worker.job_found.connect(self._on_job_imported)
            self._hunt_worker.error.connect(self._on_worker_failed)
            self._hunt_worker.finished.connect(self._on_hunt_finished)
            self._hunt_worker.start()
            
        except Exception as e:
            self._on_worker_failed(str(e))

    def toggle_job_hunt(self) -> None:
        if self._hunt_worker and self._hunt_worker.isRunning():
            self.stop_job_hunt()
        else:
            self.start_job_hunt()

    def stop_job_hunt(self) -> None:
        if self._hunt_worker and self._hunt_worker.isRunning():
            self.add_agent_message("Stopping Job Hunt... aborting active tasks.")
            self._hunt_worker.stop()
            self._toggle_btn.setEnabled(False)
            self._toggle_btn.setText("Stopping...")
            self._next_btn.setEnabled(False)

    def move_to_next_job(self) -> None:
        if self._hunt_worker and self._hunt_worker.isRunning():
            self.add_agent_message("⏭ Move to Next Job triggered. Advancing...")
            self._hunt_worker.move_to_next()
            self._next_btn.setText("⏭ Move to Next Job")
        else:
            self.add_agent_message("No active job hunt in progress to advance.")

    def _on_job_evaluating(self, job_title: str) -> None:
        self._next_btn.setText("⏭ Move to Next Job")
        self._next_btn.setEnabled(True)

    def _on_hunt_finished(self) -> None:
        self._toggle_btn.setEnabled(True)
        self._toggle_btn.setText("Start Job Hunt")
        self._toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: #8b7ec8;
                color: #ffffff;
                border: none;
                border-radius: 11px;
                font-size: 11px;
                font-weight: 800;
                letter-spacing: 0.8px;
                text-transform: uppercase;
                padding: 10px 0;
            }
            QPushButton:hover { background-color: #5e5298; }
            QPushButton:disabled { background-color: #e8e4f7; color: #8f96a8; }
        """)
        self._next_btn.setEnabled(False)
        self._next_btn.setText("⏭ Move to Next Job")
        if self._hunt_worker:
            self._hunt_worker.deleteLater()
            self._hunt_worker = None

    def _on_job_imported(self, result: object) -> None:
        if not isinstance(result, ImportedJob):
            self._on_worker_failed("The imported job has an unexpected format.")
            return
        status = getattr(result, "status", "Analyzed")
        
        job = JobDescription(
            name=f"{result.title} at {result.company}",
            content=result.description,
            status=status,
            url=result.url,
        )
        self._runtime.plugins._context.documents.save_job_description(job)
        analysis = [result.summary, *result.recommendations[:3]]
        pdf_path = getattr(result, "pdf_path", None)
        unsupported = getattr(result, "unsupported_details", [])
        missing_skills = getattr(result, "missing_core_skills", [])
        formatting = getattr(result, "formatting_risks", [])
        self.add_job_card(
            result.title,
            result.company,
            result.match_score,
            analysis,
            str(job.id),
            pdf_path=pdf_path,
            unsupported_details=unsupported,
            missing_core_skills=missing_skills,
            formatting_risks=formatting,
        )
        if self._hunt_worker and self._hunt_worker.isRunning():
            self._next_btn.setText("⏭ Move to Next Job")
            self._next_btn.setEnabled(True)

    def _on_worker_failed(self, message: str) -> None:
        self._toggle_btn.setEnabled(True)
        self._toggle_btn.setText("Start Job Hunt")
        self._toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: #8b7ec8;
                color: #ffffff;
                border: none;
                border-radius: 11px;
                font-size: 11px;
                font-weight: 800;
                letter-spacing: 0.8px;
                text-transform: uppercase;
                padding: 10px 0;
            }
            QPushButton:hover { background-color: #5e5298; }
            QPushButton:disabled { background-color: #e8e4f7; color: #8f96a8; }
        """)
        self._next_btn.setEnabled(False)
        self._next_btn.setText("⏭ Move to Next Job")
        self.add_agent_message(f"Job workflow failed: {message}")
        self.add_agent_message(f"Job workflow failed: {message}")

    def _open_for_review(self, job_id: str) -> None:
        job = self._runtime.plugins._context.documents.get_job_description(job_id)
        if not job or not job.url:
            self._add_notice("Job URL is missing.")
            return
            
        try:
            service = self._runtime.services.get(BROWSER_SERVICE)
        except LookupError:
            self._add_notice("Browser capability is unavailable.")
            return
        if not isinstance(service, BrowserService):
            self._add_notice("Browser capability is not configured correctly.")
            return
        worker = BrowserLaunchWorker(service, job.url)
        self._browser_workers.append(worker)
        worker.completed.connect(lambda: self.add_agent_message("Job opened for your review."))
        worker.failed.connect(self._on_worker_failed)
        worker.finished.connect(lambda w=worker: self._cleanup_browser_worker(w))
        worker.start()

    def cleanup(self) -> None:
        """Gracefully interrupt and wait for all background workers before shutdown."""
        if self._hunt_worker and self._hunt_worker.isRunning():
            self._hunt_worker.requestInterruption()
            if not self._hunt_worker.wait(3000):
                self._hunt_worker.terminate()
                self._hunt_worker.wait(1000)
        for w in list(self._doc_workers):
            if w.isRunning():
                w.requestInterruption()
                if not w.wait(2000):
                    w.terminate()
                    w.wait(500)
        self._doc_workers.clear()
        for w in list(self._browser_workers):
            if w.isRunning():
                w.requestInterruption()
                if not w.wait(2000):
                    w.terminate()
                    w.wait(500)
        self._browser_workers.clear()
        if self._chat_worker and self._chat_worker.isRunning():
            self._chat_worker.requestInterruption()
            if not self._chat_worker.wait(2000):
                self._chat_worker.terminate()
                self._chat_worker.wait(500)

    def _add_notice(self, message: str) -> None:
        label = QLabel(message)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setWordWrap(True)
        label.setStyleSheet("""
            QLabel {
                background-color: #ffffff;
                color: #5c6479;
                border-left: 3px solid #8b7ec8;
                border: 1px solid rgba(139, 126, 200, 0.2);
                border-radius: 8px;
                padding: 12px;
                font-size: 13px;
            }
        """)
        self._feed_layout.addWidget(label)


class ImportedJob:
    def __init__(
        self,
        title: str,
        company: str,
        description: str,
        url: str,
        match_score: int,
        summary: str,
        recommendations: list[str],
        status: str = "Analyzed",
        pdf_path: str | None = None,
        unsupported_details: list[str] | None = None,
        missing_core_skills: list[str] | None = None,
        formatting_risks: list[str] | None = None,
    ) -> None:
        self.title = title
        self.company = company
        self.description = description
        self.url = url
        self.match_score = match_score
        self.summary = summary
        self.recommendations = recommendations
        self.status = status
        self.pdf_path = pdf_path
        self.unsupported_details = unsupported_details or []
        self.missing_core_skills = missing_core_skills or []
        self.formatting_risks = formatting_risks or []


class BrowserLaunchWorker(QThread):
    completed = Signal()
    failed = Signal(str)

    def __init__(self, browser: BrowserService, url: str) -> None:
        super().__init__()
        self.setObjectName("BrowserLaunchWorker")
        self._browser = browser
        self._url = url

    def run(self) -> None:
        try:
            asyncio.run(self._browser.launch(self._url))
        except Exception as error:
            self.failed.emit(str(error))
            return
        self.completed.emit()
