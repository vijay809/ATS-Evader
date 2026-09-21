"""Process Workspace for the human-approved job discovery loop."""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)

from openclaw.core.documents import JobDescription
from openclaw.plugins.ats import ATS_ANALYZER_SERVICE, AtsAnalyzer
from openclaw.plugins.browser import BROWSER_SERVICE, BrowserService

if TYPE_CHECKING:
    from openclaw.core.runtime import Runtime


class JobHuntWorker(QThread):
    job_found = Signal(object) # Will emit ImportedJob
    agent_message = Signal(str)
    error = Signal(str)
    finished = Signal()

    def __init__(self, browser_service: BrowserService, ats_analyzer: AtsAnalyzer, active_resume: str, role: str, location: str, min_exp: int, win_x: int = 0, win_y: int = 0, win_w: int = 1280, win_h: int = 800):
        super().__init__()
        self.browser = browser_service
        self.analyzer = ats_analyzer
        self.active_resume = active_resume
        self.role = role
        self.location = location
        self.min_exp = min_exp
        self.win_x = win_x
        self.win_y = win_y
        self.win_w = win_w
        self.win_h = win_h

    def run(self):
        asyncio.run(self.do_hunt())
        self.finished.emit()

    async def do_hunt(self):
        try:
            self.agent_message.emit(f"Launching browser to search for '{self.role}' in '{self.location}'...")
            links = await self.browser.search_naukri_jobs(
                self.role, self.location, max_results=3,
                win_x=self.win_x, win_y=self.win_y, win_w=self.win_w, win_h=self.win_h
            )
            
            if not links:
                self.agent_message.emit("No matching jobs found on the current page.")
                return
                
            self.agent_message.emit(f"Found {len(links)} matching job links. Extracting details...")
            
            for i, link in enumerate(links):
                if not self.browser.page or self.browser.page.is_closed():
                    raise RuntimeError("Browser was closed by the user.")
                    
                jd = await self.browser.extract_naukri_jd(link)
                if not jd['description']:
                    continue
                    
                if not self.browser.page or self.browser.page.is_closed():
                    raise RuntimeError("Browser was closed by the user.")
                
                import logging
                logger = logging.getLogger("process_workspace")
                logger.info(f"Extracting eligibility facts for: {jd['title']} at {jd['company']}")
                
                try:
                    facts = await self.analyzer.check_eligibility(jd['description'])
                except Exception as e:
                    logger.error(f"Eligibility extraction failed: {e}")
                    facts = None
                    
                if facts:
                    if facts.min_years_experience is not None and facts.min_years_experience > self.min_exp:
                        skip_msg = f"Skipping '{jd['title']}' - Requires {facts.min_years_experience} years exp (You have {self.min_exp})."
                        self.agent_message.emit(skip_msg)
                        logger.info(skip_msg)
                        continue
                        
                    if facts.location_type and facts.location_type.lower() != "remote" and self.location.lower() == "remote":
                        skip_msg = f"Skipping '{jd['title']}' - It is {facts.location_type} but you require Remote."
                        self.agent_message.emit(skip_msg)
                        logger.info(skip_msg)
                        continue
                        
                self.agent_message.emit(f"[{i+1}/{len(links)}] Scoring: {jd['title']} at {jd['company']}...")
                
                # Poll browser state while LLM analyzes
                analysis_task = asyncio.create_task(self.analyzer.analyze(self.active_resume, jd['description']))
                while not analysis_task.done():
                    if not self.browser.page or self.browser.page.is_closed():
                        analysis_task.cancel()
                        raise RuntimeError("Browser was closed by the user.")
                    await asyncio.sleep(1)
                    
                analysis = analysis_task.result()
                
                job = ImportedJob(
                    jd['title'],
                    jd['company'],
                    jd['description'],
                    link,
                    analysis.match_score,
                    analysis.summary,
                    analysis.recommendations
                )
                self.job_found.emit(job)
                
            self.agent_message.emit("Automated search complete. Awaiting further instructions.")
                
        except asyncio.CancelledError:
            self.error.emit("Job hunt was cancelled.")
        except Exception as e:
            self.error.emit(str(e))

class AiChatWorker(QThread):
    agent_message = Signal(str)
    error = Signal(str)
    finished = Signal()

    def __init__(self, navigator: object, command: str):
        super().__init__()
        self.navigator = navigator
        self.command = command

    def run(self):
        asyncio.run(self.do_chat())
        self.finished.emit()

    async def do_chat(self):
        try:
            self.agent_message.emit(f"Processing command: '{self.command}'...")
            
            # Using the actual SemanticNavigator
            def stream_callback(msg: str):
                self.agent_message.emit(msg)
                
            result = await self.navigator.execute_goal(self.command, max_steps=10, emit_cb=stream_callback)
            
            if not result.success:
                self.agent_message.emit(f"Execution stopped. {result.error or ''}")

        except Exception as e:
            self.error.emit(str(e))

class DocumentGeneratorWorker(QThread):
    agent_message = Signal(str)
    error = Signal(str)
    finished = Signal()

    def __init__(self, analyzer: AtsAnalyzer, active_resume: str, job_description: str, doc_type: str):
        super().__init__()
        self.analyzer = analyzer
        self.active_resume = active_resume
        self.job_description = job_description
        self.doc_type = doc_type

    def run(self):
        try:
            if self.doc_type == "cover_letter":
                self.agent_message.emit("Drafting a punchy cover letter based on your master resume and the job description...")
                result = self.analyzer.generate_cover_letter(self.active_resume, self.job_description)
                msg = "📝 **Generated Cover Letter:**\n\n" + result.cover_letter
                if result.warnings:
                    msg += "\n\n*Warnings: " + ", ".join(result.warnings) + "*"
                self.agent_message.emit(msg)
            elif self.doc_type == "tailor_cv":
                self.agent_message.emit("Rewriting and optimizing your CV to match the job description's keywords...")
                result = self.analyzer.tailor_resume(self.active_resume, self.job_description)
                msg = "📄 **Tailored CV (Markdown format):**\n\n" + result.tailored_resume
                if result.change_summary:
                    msg += "\n\n*Changes made:*\n- " + "\n- ".join(result.change_summary)
                if result.warnings:
                    msg += "\n\n*Warnings: " + ", ".join(result.warnings) + "*"
                self.agent_message.emit(msg)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()

class ProcessWorkspace(QWidget):
    """The central dashboard for agent interaction and job approvals."""

    def __init__(self, runtime: Runtime) -> None:
        super().__init__()
        self._runtime = runtime
        self._worker: QThread | None = None
        self._chat_worker: QThread | None = None

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

        sidebar_layout.addStretch()

        self._start_btn = QPushButton("Start Job Hunt")
        self._start_btn.setMinimumHeight(48)
        self._start_btn.setStyleSheet("""
            QPushButton {
                background-color: #adc6ff; color: #002e69; 
                border-radius: 8px; font-size: 16px; font-weight: bold;
            }
            QPushButton:disabled { background-color: #555; color: #aaa; }
        """)
        self._start_btn.clicked.connect(self.start_job_hunt)
        sidebar_layout.addWidget(self._start_btn)
        
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

    def _reset_browser(self):
        try:
            browser = self._runtime.services.get(BROWSER_SERVICE)
            if isinstance(browser, BrowserService):
                browser.reset_session()
                self._add_notice("Browser session and cookies have been wiped. The next launch will be a fresh login.")
        except LookupError:
            self._add_notice("Browser capability is unavailable.")

    def add_user_message(self, text: str):
        msg = QLabel(text)
        msg.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        msg.setWordWrap(True)
        msg.setStyleSheet("color: #ffffff; background-color: #3b4252; border-radius: 8px; padding: 12px; margin-left: 40px;")
        self._feed_layout.addWidget(msg)

    def add_agent_message(self, text: str):
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
        
        try:
            browser = self._runtime.services.get(BROWSER_SERVICE)
            navigator = self._runtime.services.get("browser.navigator")
        except LookupError:
            self.add_agent_message("Browser capability is unavailable.")
            return

        self._chat_input.setEnabled(False)
        self._chat_worker = AiChatWorker(navigator, text)
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

        # Analysis
        for point in analysis:
            p_lbl = QLabel(f"• {point}")
            p_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            p_lbl.setWordWrap(True)
            p_lbl.setStyleSheet("color: #c1c6d7; font-size: 14px; border: none;")
            layout.addWidget(p_lbl)

        # Actions
        actions_layout = QHBoxLayout()
        approve_btn = QPushButton("Review in Browser")
        approve_btn.setMinimumHeight(40)
        approve_btn.setStyleSheet("background-color: #4b8eff; color: white; border-radius: 6px; font-weight: bold;")
        
        cover_letter_btn = QPushButton("Write Cover Letter")
        cover_letter_btn.setMinimumHeight(40)
        cover_letter_btn.setStyleSheet("background-color: #5b3a6e; color: white; border-radius: 6px; font-weight: bold;")
        
        tailor_cv_btn = QPushButton("Tailor CV")
        tailor_cv_btn.setMinimumHeight(40)
        tailor_cv_btn.setStyleSheet("background-color: #3b5a4b; color: white; border-radius: 6px; font-weight: bold;")
        
        skip_btn = QPushButton("Skip")
        def handle_skip():
            job = self._runtime.plugins._context.documents.get_job_description(job_id)
            if job:
                job.status = "Skipped"
                self._runtime.plugins._context.documents.save_job_description(job)
            card.deleteLater()
            
        approve_btn.clicked.connect(lambda: self._open_for_review(job_id))
        skip_btn.clicked.connect(handle_skip)
        
        cover_letter_btn.clicked.connect(lambda: self._generate_document("cover_letter", job_id))
        tailor_cv_btn.clicked.connect(lambda: self._generate_document("tailor_cv", job_id))
        
        actions_layout.addWidget(approve_btn)
        actions_layout.addWidget(cover_letter_btn)
        actions_layout.addWidget(tailor_cv_btn)
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
                
            self._worker = DocumentGeneratorWorker(analyzer, active_resume.raw_content, job.content, doc_type)
            self._worker.agent_message.connect(self.add_agent_message)
            self._worker.error.connect(self._on_worker_failed)
            self._worker.start()
        except Exception as e:
            self._on_worker_failed(str(e))

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

            self._start_btn.setEnabled(False)
            self._start_btn.setText("Auto-Hunting...")
            self.add_agent_message(f"Beginning automated job hunt for '{role}' in '{location}'...")
            
            self._worker = JobHuntWorker(
                browser, analyzer, active_resume.raw_content, role, location, min_exp,
                win_x=avail_geo.x() + w, win_y=y_pos, win_w=w, win_h=h
            )
            self._worker.agent_message.connect(self.add_agent_message)
            self._worker.job_found.connect(self._on_job_imported)
            self._worker.error.connect(self._on_worker_failed)
            self._worker.finished.connect(self._on_hunt_finished)
            self._worker.start()
            
        except Exception as e:
            self._on_worker_failed(str(e))

    def _on_hunt_finished(self) -> None:
        self._start_btn.setEnabled(True)
        self._start_btn.setText("Start Job Hunt")
        self._worker = None

    def _on_job_imported(self, result: object) -> None:
        if not isinstance(result, ImportedJob):
            self._on_worker_failed("The imported job has an unexpected format.")
            return
        job = JobDescription(
            name=f"{result.title} at {result.company}",
            content=result.description,
            status="Analyzed",
            url=result.url,
        )
        self._runtime.plugins._context.documents.save_job_description(job)
        analysis = [result.summary, *result.recommendations[:3]]
        self.add_job_card(result.title, result.company, result.match_score, analysis, str(job.id))

    def _on_worker_failed(self, message: str) -> None:
        self._start_btn.setEnabled(True)
        self._start_btn.setText("Start Job Hunt")
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
        self._worker = BrowserLaunchWorker(service, job.url)
        self._worker.completed.connect(lambda: self.add_agent_message("Job opened for your review."))
        self._worker.failed.connect(self._on_worker_failed)
        self._worker.start()

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
    ) -> None:
        self.title = title
        self.company = company
        self.description = description
        self.url = url
        self.match_score = match_score
        self.summary = summary
        self.recommendations = recommendations


class BrowserLaunchWorker(QThread):
    completed = Signal()
    failed = Signal(str)

    def __init__(self, browser: BrowserService, url: str) -> None:
        super().__init__()
        self._browser = browser
        self._url = url

    def run(self) -> None:
        try:
            asyncio.run(self._browser.launch(self._url))
        except Exception as error:  # noqa: BLE001
            self.failed.emit(str(error))
            return
        self.completed.emit()
