"""Process Workspace for the human-approved job discovery loop."""
from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QShowEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
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

        # -- LEFT SIDEBAR (Preferences) --
        sidebar = QWidget()
        sidebar.setStyleSheet("background-color: #1a1a1a; border-right: 1px solid #333;")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(24, 24, 24, 24)
        sidebar_layout.setSpacing(16)

        header = QLabel("Target Profile")
        header.setStyleSheet("font-size: 24px; font-weight: bold; color: #e5e2e1; border: none;")
        sidebar_layout.addWidget(header)

        # Dynamic Preferences area (we will populate this from DB)
        self._pref_layout = QVBoxLayout()
        sidebar_layout.addLayout(self._pref_layout)
        
        self._threshold_lbl = QLabel("ATS Threshold: 50%")
        self._threshold_lbl.setStyleSheet("color: white; font-weight: bold; border: none;")
        self._threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self._threshold_slider.setRange(5, 95)
        self._threshold_slider.setSingleStep(5)
        self._threshold_slider.setPageStep(5)
        self._threshold_slider.setTickInterval(5)
        self._threshold_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._threshold_slider.setValue(50)
        self._threshold_slider.valueChanged.connect(
            lambda v: self._threshold_lbl.setText(f"ATS Threshold: {v}%")
        )
        sidebar_layout.addWidget(self._threshold_lbl)
        sidebar_layout.addWidget(self._threshold_slider)

        sidebar_layout.addStretch()

        self._toggle_btn = QPushButton("Start Job Hunt")
        self._toggle_btn.setMinimumHeight(48)
        self._toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: #adc6ff; color: #002e69; 
                border-radius: 8px; font-size: 16px; font-weight: bold;
            }
            QPushButton:hover { background-color: #cfdcff; }
            QPushButton:disabled { background-color: #555; color: #aaa; }
        """)
        self._toggle_btn.clicked.connect(self.toggle_job_hunt)
        sidebar_layout.addWidget(self._toggle_btn)

        self._next_btn = QPushButton("⏭ Stop & Move to Next")
        self._next_btn.setMinimumHeight(44)
        self._next_btn.setStyleSheet("""
            QPushButton {
                background-color: #f59e0b; color: #1c1917; 
                border-radius: 8px; font-size: 14px; font-weight: bold;
            }
            QPushButton:hover { background-color: #fbbf24; }
            QPushButton:disabled { background-color: #2a2a2a; color: #555555; border: 1px solid #3d3d3d; }
        """)
        self._next_btn.setEnabled(False)
        self._next_btn.clicked.connect(self.move_to_next_job)
        sidebar_layout.addWidget(self._next_btn)
        
        self._reset_btn = QPushButton("Reset Browser")
        self._reset_btn.setMinimumHeight(40)
        self._reset_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent; color: #ffb4ab; 
                border: 1px solid #ffb4ab; border-radius: 8px; font-size: 14px; font-weight: bold;
            }
            QPushButton:hover { background-color: rgba(255, 180, 171, 0.1); }
        """)
        self._reset_btn.clicked.connect(self._reset_browser)
        sidebar_layout.addWidget(self._reset_btn)

        self._folder_btn = QPushButton("Open Outputs Folder")
        self._folder_btn.setMinimumHeight(40)
        self._folder_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent; color: #adc6ff; 
                border: 1px solid #adc6ff; border-radius: 8px; font-size: 14px; font-weight: bold;
            }
            QPushButton:hover { background-color: rgba(173, 198, 255, 0.1); }
        """)
        self._folder_btn.clicked.connect(self._open_outputs_folder)
        sidebar_layout.addWidget(self._folder_btn)

        # -- RIGHT MAIN AREA (Chat/Feed) --
        main_area = QWidget()
        main_area.setStyleSheet("background-color: #131313;")
        main_area_layout = QVBoxLayout(main_area)
        main_area_layout.setContentsMargins(24, 24, 24, 24)
        
        # Scrollable feed
        feed_scroll = QScrollArea()
        feed_scroll.setWidgetResizable(True)
        feed_scroll.setStyleSheet("border: none; background: transparent;")
        
        self._feed_widget = QWidget()
        self._feed_widget.setStyleSheet("background: transparent;")
        self._feed_layout = QVBoxLayout(self._feed_widget)
        self._feed_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        feed_scroll.setWidget(self._feed_widget)
        
        main_area_layout.addWidget(feed_scroll, stretch=1)

        # Chat Input
        chat_layout = QHBoxLayout()
        self._chat_input = QLineEdit()
        self._chat_input.setPlaceholderText("Chat with AI to guide the job hunt or ask questions...")
        self._chat_input.setMinimumHeight(48)
        self._chat_input.setStyleSheet("""
            QLineEdit {
                background-color: #1c1b1b; color: white; border: 1px solid #333; 
                border-radius: 24px; padding: 0 16px; font-size: 14px;
            }
        """)
        
        send_btn = QPushButton("Send")
        send_btn.setMinimumHeight(48)
        send_btn.setStyleSheet("background-color: transparent; color: #adc6ff; font-weight: bold; border: none;")
        
        chat_layout.addWidget(self._chat_input)
        chat_layout.addWidget(send_btn)
        send_btn.clicked.connect(self.send_chat_message)
        self._chat_input.returnPressed.connect(self.send_chat_message)
        main_area_layout.addLayout(chat_layout)

        # Add to splitter
        splitter.addWidget(sidebar)
        splitter.addWidget(main_area)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        main_layout.addWidget(splitter)
        self.refresh_preferences()
        self._add_notice("Click 'Start Job Hunt' to let the agent auto-search based on your Target Profile. Chat with me below to guide the process (e.g. 'Apply to this one').")

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.refresh_preferences()

    def refresh_preferences(self) -> None:
        """Load preferences from SQLite and display them in the sidebar."""
        # Clear existing
        while self._pref_layout.count():
            child = self._pref_layout.takeAt(0)
            if child is not None:
                widget = child.widget()
                if widget is not None:
                    widget.deleteLater()

        try:
            import json
            active_resume = self._runtime.plugins._context.documents.get_active_structured_resume()
            if not active_resume:
                return
            
            parsed = json.loads(active_resume.parsed_json)
            if isinstance(parsed, dict) and "preferences" in parsed:
                prefs = parsed["preferences"]
            else:
                # Fallback to global DB preferences for older parses
                prefs = {p.key: p.value for p in self._runtime.plugins._context.documents.get_preferences()}
                
            for k, v in prefs.items():
                card = QFrame()
                card.setStyleSheet("background-color: #2a2a2a; border-radius: 8px; padding: 12px; border: none;")
                card_layout = QVBoxLayout(card)
                card_layout.setContentsMargins(0,0,0,0)
                
                k_lbl = QLabel(k.upper())
                k_lbl.setStyleSheet("color: #8b90a0; font-size: 10px; font-weight: bold; font-family: monospace; border: none;")
                v_lbl = QLabel(v)
                v_lbl.setWordWrap(True)
                v_lbl.setStyleSheet("color: white; font-size: 14px; border: none;")
                
                card_layout.addWidget(k_lbl)
                card_layout.addWidget(v_lbl)
                self._pref_layout.addWidget(card)
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
        msg.setStyleSheet("color: #ffffff; background-color: #3b4252; border-radius: 8px; padding: 12px; margin-left: 40px;")
        self._feed_layout.addWidget(msg)

    def add_agent_message(self, text: str) -> None:
        msg = QLabel(f"🤖 {text}")
        msg.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        msg.setWordWrap(True)
        msg.setStyleSheet("color: #adc6ff; background-color: transparent; padding: 8px; font-style: italic;")
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
        card.setStyleSheet("background-color: #1c1b1b; border: 1px solid #adc6ff; border-radius: 12px; padding: 16px;")
        layout = QVBoxLayout(card)
        
        # Header
        header_layout = QHBoxLayout()
        title_lbl = QLabel(f"{title} @ {company}")
        title_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: white; border: none;")
        score_lbl = QLabel(f"{match_score}% Match")
        score_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #ecb2ff; border: none;")
        
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()
        header_layout.addWidget(score_lbl)
        layout.addLayout(header_layout)

        # Analysis Summary
        for point in analysis:
            p_lbl = QLabel(f"• {point}")
            p_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            p_lbl.setWordWrap(True)
            p_lbl.setStyleSheet("color: #c1c6d7; font-size: 14px; border: none;")
            layout.addWidget(p_lbl)

        # Gap & Flag Report
        has_gaps = bool(missing_core_skills or unsupported_details or formatting_risks)
        if has_gaps:
            gap_frame = QFrame()
            gap_frame.setStyleSheet("""
                QFrame {
                    background-color: rgba(30, 20, 20, 0.6);
                    border: 1px solid rgba(255, 180, 171, 0.35);
                    border-radius: 8px;
                    padding: 8px;
                    margin-top: 6px;
                    margin-bottom: 6px;
                }
            """)
            gap_layout = QVBoxLayout(gap_frame)
            gap_layout.setContentsMargins(10, 8, 10, 8)
            gap_layout.setSpacing(5)

            gap_header = QLabel("⚠️ GAP & FLAG REPORT")
            gap_header.setStyleSheet("color: #ffb4ab; font-size: 12px; font-weight: bold; border: none; letter-spacing: 0.5px;")
            gap_layout.addWidget(gap_header)

            if missing_core_skills:
                skills_str = ", ".join(missing_core_skills)
                skills_lbl = QLabel(f"❌ <b>Missing Core Skills:</b> <span style='color: #ffadc6;'>{skills_str}</span>")
                skills_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                skills_lbl.setWordWrap(True)
                skills_lbl.setStyleSheet("color: #e5e2e1; font-size: 13px; border: none;")
                gap_layout.addWidget(skills_lbl)

            if unsupported_details:
                for item in unsupported_details:
                    unsup_lbl = QLabel(f"⚠️ <b>Unsupported Requirement:</b> {item}")
                    unsup_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                    unsup_lbl.setWordWrap(True)
                    unsup_lbl.setStyleSheet("color: #ffb595; font-size: 13px; border: none;")
                    gap_layout.addWidget(unsup_lbl)

            if formatting_risks:
                for item in formatting_risks:
                    risk_lbl = QLabel(f"🚩 <b>ATS / Formatting Risk:</b> {item}")
                    risk_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                    risk_lbl.setWordWrap(True)
                    risk_lbl.setStyleSheet("color: #e0c48c; font-size: 13px; border: none;")
                    gap_layout.addWidget(risk_lbl)

            layout.addWidget(gap_frame)
        else:
            clean_badge = QLabel("✓ Zero Critical Gaps or Formatting Risks Detected")
            clean_badge.setStyleSheet("color: #a5d6a7; font-size: 12px; font-weight: bold; padding: 4px 0; border: none;")
            layout.addWidget(clean_badge)

        # Actions
        actions_layout = QHBoxLayout()
        approve_btn = QPushButton("Review in Browser")
        approve_btn.setMinimumHeight(40)
        approve_btn.setStyleSheet("background-color: #4b8eff; color: white; border-radius: 6px; font-weight: bold;")
        
        applied_btn = QPushButton("Mark Applied")
        applied_btn.setMinimumHeight(40)
        applied_btn.setStyleSheet("background-color: #2e7d32; color: white; border-radius: 6px; font-weight: bold;")

        cover_letter_btn = QPushButton("Write Cover Letter")
        cover_letter_btn.setMinimumHeight(40)
        cover_letter_btn.setStyleSheet("background-color: #5b3a6e; color: white; border-radius: 6px; font-weight: bold;")
        
        tailor_cv_btn = QPushButton("Tailor CV")
        tailor_cv_btn.setMinimumHeight(40)
        tailor_cv_btn.setStyleSheet("background-color: #3b5a4b; color: white; border-radius: 6px; font-weight: bold;")
        
        skip_btn = QPushButton("Skip")
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
            applied_btn.setStyleSheet("background-color: #1b5e20; color: #a5d6a7; border-radius: 6px; font-weight: bold;")
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
            open_cv_btn.setMinimumHeight(40)
            open_cv_btn.setStyleSheet("background-color: rgba(173, 198, 255, 0.15); color: #adc6ff; border: 1px solid rgba(173, 198, 255, 0.35); border-radius: 6px; font-weight: bold;")
            open_cv_btn.clicked.connect(lambda checked=False, p=pdf_path: QDesktopServices.openUrl(QUrl.fromLocalFile(p)))
            actions_layout.addWidget(open_cv_btn)

        actions_layout.addWidget(cover_letter_btn)
        actions_layout.addWidget(tailor_cv_btn)

        next_job_btn = QPushButton("⏭ Move to Next")
        next_job_btn.setMinimumHeight(40)
        next_job_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(245, 158, 11, 0.15); 
                color: #f59e0b; 
                border: 1px solid rgba(245, 158, 11, 0.4); 
                border-radius: 6px; 
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(245, 158, 11, 0.3);
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

            self._toggle_btn.setText("⏹ Stop Hunt")
            self._toggle_btn.setStyleSheet("""
                QPushButton {
                    background-color: #690000; color: #ffadc6; 
                    border-radius: 8px; font-size: 16px; font-weight: bold;
                }
                QPushButton:hover { background-color: #850000; }
                QPushButton:disabled { background-color: #444; color: #888; }
            """)
            self._next_btn.setEnabled(True)
            self._next_btn.setText("⏭ Stop & Move to Next")
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
            self.add_agent_message("⏭ Stop & Move to Next triggered. Advancing...")
            self._hunt_worker.move_to_next()
            self._next_btn.setText("⏭ Stop & Move to Next")
        else:
            self.add_agent_message("No active job hunt in progress to advance.")

    def _on_job_evaluating(self, job_title: str) -> None:
        self._next_btn.setText("⏭ Stop & Move to Next")
        self._next_btn.setEnabled(True)

    def _on_hunt_finished(self) -> None:
        self._toggle_btn.setEnabled(True)
        self._toggle_btn.setText("Start Job Hunt")
        self._toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: #adc6ff; color: #002e69; 
                border-radius: 8px; font-size: 16px; font-weight: bold;
            }
            QPushButton:hover { background-color: #cfdcff; }
            QPushButton:disabled { background-color: #555; color: #aaa; }
        """)
        self._next_btn.setEnabled(False)
        self._next_btn.setText("⏭ Stop & Move to Next")
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
                background-color: #adc6ff; color: #002e69; 
                border-radius: 8px; font-size: 16px; font-weight: bold;
            }
            QPushButton:hover { background-color: #cfdcff; }
            QPushButton:disabled { background-color: #555; color: #aaa; }
        """)
        self._next_btn.setEnabled(False)
        self._next_btn.setText("⏭ Stop & Move to Next")
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
        label.setStyleSheet("color: #c1c6d7; background-color: #1c1b1b; border-radius: 8px; padding: 12px;")
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
