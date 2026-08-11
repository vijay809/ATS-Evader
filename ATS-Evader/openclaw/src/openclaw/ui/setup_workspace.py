"""Setup workspace matching the Stitch AI design."""
from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING
from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPlainTextEdit, QPushButton, QMessageBox, QScrollArea, QFrame, QSizePolicy
)

from openclaw.core.documents import StructuredResume, Preference
from openclaw.plugins.ats import ATS_ANALYZER_SERVICE, AtsAnalyzer, ParsedResumeData

if TYPE_CHECKING:
    from openclaw.core.runtime import Runtime


from openclaw.ui.terminal_loader import TerminalLoaderOverlay

class HistoryProfileWidget(QFrame):
    """Expandable accordion for historical profiles."""
    def __init__(self, resume: StructuredResume, on_set_active: callable, on_delete: callable) -> None:
        super().__init__()
        self.resume = resume
        self.on_set_active = on_set_active
        self.on_delete = on_delete
        self.is_expanded = False
        
        self.setStyleSheet("""
            HistoryProfileWidget {
                background-color: transparent;
                border: 1px solid rgba(255,255,255,0.05);
                border-radius: 8px;
            }
            HistoryProfileWidget:hover {
                background-color: rgba(255,255,255,0.02);
            }
        """)
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(16, 16, 16, 16)
        self.main_layout.setSpacing(12)
        
        # Header (Always visible)
        self.header_widget = QWidget()
        header_layout = QHBoxLayout(self.header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        info_layout = QVBoxLayout()
        name_lbl = QLabel(resume.name)
        name_lbl.setStyleSheet("color: #e5e2e1; font-size: 14px; font-weight: bold; border: none;")
        
        # Parse some basic info from JSON
        role = "Historical Resume"
        try:
            import json
            parsed = json.loads(resume.parsed_json)
            if isinstance(parsed, dict) and "preferences" in parsed:
                role = parsed["preferences"].get("Target Role", "Historical Resume")
        except Exception:
            pass
            
        time_str = datetime.fromtimestamp(resume.created_at).strftime("%b %d, %H:%M")
        sub_lbl = QLabel(f"{time_str} • {role}")
        sub_lbl.setStyleSheet("color: #8b90a0; font-family: monospace; font-size: 11px; border: none;")
        
        info_layout.addWidget(name_lbl)
        info_layout.addWidget(sub_lbl)
        
        self.expand_icon = QLabel("▼")
        self.expand_icon.setStyleSheet("color: #8b90a0; font-size: 12px; border: none;")
        
        header_layout.addLayout(info_layout)
        header_layout.addStretch()
        header_layout.addWidget(self.expand_icon)
        
        self.main_layout.addWidget(self.header_widget)
        
        # Details (Hidden by default)
        self.details_widget = QWidget()
        details_layout = QVBoxLayout(self.details_widget)
        details_layout.setContentsMargins(0, 8, 0, 0)
        
        actions_layout = QHBoxLayout()
        actions_layout.setContentsMargins(0, 0, 0, 0)
        
        set_active_btn = QPushButton("Set as Active Profile")
        set_active_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(173, 198, 255, 0.1);
                border: 1px solid rgba(173, 198, 255, 0.2);
                color: #adc6ff;
                border-radius: 6px;
                padding: 8px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover { background-color: rgba(173, 198, 255, 0.2); }
        """)
        set_active_btn.clicked.connect(lambda: self.on_set_active(str(self.resume.id)))
        
        delete_btn = QPushButton("Delete")
        delete_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 180, 171, 0.1);
                border: 1px solid rgba(255, 180, 171, 0.2);
                color: #ffb4ab;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover { background-color: rgba(255, 180, 171, 0.2); }
        """)
        delete_btn.clicked.connect(lambda: self.on_delete(str(self.resume.id)))
        
        actions_layout.addWidget(set_active_btn)
        actions_layout.addWidget(delete_btn)
        
        details_layout.addLayout(actions_layout)
        
        self.details_widget.hide()
        self.main_layout.addWidget(self.details_widget)
        
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_expanded = not self.is_expanded
            if self.is_expanded:
                self.details_widget.show()
                self.expand_icon.setText("▲")
            else:
                self.details_widget.hide()
                self.expand_icon.setText("▼")


class SetupWorkspace(QWidget):
    """The Setup screen for parsing a master resume."""

    def __init__(self, runtime: 'Runtime') -> None:
        super().__init__()
        self._runtime = runtime
        
        self._loader = TerminalLoaderOverlay(self)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Header
        header = QLabel("System Setup")
        header.setStyleSheet("font-size: 32px; font-weight: 600; color: #e5e2e1; border: none;")
        
        desc = QLabel("Initialize the AI matching engine by providing a comprehensive master resume.")
        desc.setStyleSheet("font-size: 16px; color: #c1c6d7; border: none;")
        desc.setWordWrap(True)

        layout.addWidget(header)
        layout.addWidget(desc)

        # Main Input Area
        self._text_area = QPlainTextEdit()
        self._text_area.setPlaceholderText("Paste master resume, core job description, or structural requirements here...")
        self._text_area.setMinimumHeight(200)
        self._text_area.setStyleSheet("background-color: #080808; color: #e5e2e1; padding: 16px; border-radius: 8px;")
        
        layout.addWidget(self._text_area)

        # Buttons
        btn_layout = QHBoxLayout()
        self._clear_btn = QPushButton("Clear")
        self._clear_btn.clicked.connect(self._text_area.clear)
        self._clear_btn.setStyleSheet("""
            QPushButton { background-color: #2a2a2a; color: white; border-radius: 8px; padding: 12px 24px; font-weight: bold; }
            QPushButton:hover { background-color: #353534; }
        """)
        
        self._parse_btn = QPushButton("Parse & Extract Details")
        self._parse_btn.setMinimumHeight(48)
        self._parse_btn.setStyleSheet("background-color: #005bc1; color: white; border-radius: 12px; font-size: 16px; font-weight: bold;")
        self._parse_btn.clicked.connect(self._on_parse)
        
        btn_layout.addWidget(self._clear_btn)
        btn_layout.addWidget(self._parse_btn, stretch=1)
        layout.addLayout(btn_layout)

        # Profiles Section
        self._profiles_container = QWidget()
        self._profiles_layout = QVBoxLayout(self._profiles_container)
        self._profiles_layout.setContentsMargins(0, 16, 0, 0)
        self._profiles_layout.setSpacing(24)
        layout.addWidget(self._profiles_container)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_profiles()

    def _refresh_profiles(self) -> None:
        # Clear layout
        while self._profiles_layout.count():
            item = self._profiles_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        try:
            repo = self._runtime.plugins._context.documents
            resumes = repo.list_structured_resumes()
        except Exception:
            return
            
        if not resumes:
            return
            
        active_resume = next((r for r in resumes if r.is_active), None)
        history = [r for r in resumes if not r.is_active]
        
        if active_resume:
            self._build_active_profile(active_resume)
            
        if history:
            self._build_history(history)

    def _build_active_profile(self, resume: StructuredResume) -> None:
        # Try to pull role from active resume's preferences
        try:
            import json
            parsed = json.loads(resume.parsed_json)
            if isinstance(parsed, dict) and "preferences" in parsed:
                role = parsed["preferences"].get("Target Role", "Professional")
            else:
                repo = self._runtime.plugins._context.documents
                prefs = {p.key: p.value for p in repo.get_preferences()}
                role = prefs.get("Target Role", "Professional")
        except Exception:
            role = "Professional"

        container = QFrame()
        container.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(236, 178, 255, 0.15);
                border-radius: 12px;
            }
        """)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        
        header_layout = QHBoxLayout()
        icon = QLabel("👤")
        icon.setStyleSheet("border: none; background: transparent;")
        title = QLabel("Currently Active Profile")
        title.setStyleSheet("color: #ecb2ff; font-family: monospace; font-size: 12px; font-weight: bold; text-transform: uppercase; border: none;")
        header_layout.addWidget(icon)
        header_layout.addWidget(title)
        header_layout.addStretch()
        layout.addLayout(header_layout)
        
        info_layout = QHBoxLayout()
        name_lbl = QLabel(resume.name)
        name_lbl.setStyleSheet("color: #e5e2e1; font-size: 24px; font-weight: bold; border: none;")
        
        role_lbl = QLabel(role)
        role_lbl.setStyleSheet("color: #adc6ff; font-family: monospace; font-size: 14px; border: none;")
        
        info_layout.addWidget(name_lbl)
        info_layout.addWidget(role_lbl)
        info_layout.addStretch()
        layout.addLayout(info_layout)
        
        self._profiles_layout.addWidget(container)

    def _build_history(self, history: list[StructuredResume]) -> None:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        
        header_layout = QHBoxLayout()
        title = QLabel("Recent History")
        title.setStyleSheet("color: #8b90a0; font-family: monospace; font-size: 10px; font-weight: bold; text-transform: uppercase; border: none;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        layout.addLayout(header_layout)
        
        for resume in history:
            hw = HistoryProfileWidget(resume, self._on_set_active, self._on_delete_profile)
            layout.addWidget(hw)
            
        self._profiles_layout.addWidget(container)
        
    def _on_set_active(self, resume_id: str) -> None:
        try:
            repo = self._runtime.plugins._context.documents
            repo.set_active_structured_resume(resume_id)
            self._refresh_profiles()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to set active profile: {e}")

    def _on_delete_profile(self, resume_id: str) -> None:
        reply = QMessageBox.question(self, 'Delete Profile', 'Are you sure you want to delete this historical profile?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                repo = self._runtime.plugins._context.documents
                repo.delete_structured_resume(resume_id)
                self._refresh_profiles()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to delete profile: {e}")

    def _on_parse(self) -> None:
        text = self._text_area.toPlainText().strip()
        if not text:
            return

        try:
            analyzer = self._runtime.services.get(ATS_ANALYZER_SERVICE)
        except LookupError:
            QMessageBox.warning(self, "Error", "ATS Analyzer service not available.")
            return

        import typing
        from openclaw.plugins.ats import AtsAnalyzer
        from openclaw.plugins.ollama import OLLAMA_CLIENT_SERVICE, OllamaClient
        
        analyzer_typed = typing.cast(AtsAnalyzer, analyzer)
        try:
            ollama = typing.cast(OllamaClient, self._runtime.services.get(OLLAMA_CLIENT_SERVICE))
        except LookupError:
            QMessageBox.warning(self, "Error", "Ollama service not available.")
            return

        state = {}

        def check_ollama_availability() -> None:
            if not ollama.check_ollama_availability():
                raise Exception("Ollama executable not found in system PATH. Please install Ollama.")

        def check_and_boot_server() -> None:
            server_up = False
            try:
                server_up = ollama.check_connection()
            except Exception:
                pass
            
            if not server_up:
                ollama.boot_ollama()
                import time
                for _ in range(10):
                    time.sleep(1)
                    try:
                        if ollama.check_connection():
                            return
                    except Exception:
                        pass
                raise Exception("Started Ollama but it did not become ready within 10 seconds.")

        def verify_ai_model() -> None:
            models = ollama.get_available_models()
            if not models:
                raise Exception("No AI models installed in local Ollama.")
            if "gemma4:12b" in models:
                state['model'] = "gemma4:12b"
            else:
                state['model'] = models[0]

        def parse_resume() -> None:
            model = state.get('model', 'gemma4:12b')
            result = analyzer_typed.parse_master_resume(text, model)
            state['result'] = result

        def save_data() -> None:
            result = state.get('result')
            if not result or not hasattr(result, "preferences"):
                raise Exception("Invalid parsed data.")
            
            parsed = typing.cast(ParsedResumeData, result)
            candidate_name = parsed.preferences.get("Candidate Name", "Master Resume")
            
            repo = self._runtime.plugins._context.documents
            # Store the entire ParsedResumeData payload so preferences move with the resume
            sr = StructuredResume(raw_content=text, parsed_json=result.model_dump_json(), name=candidate_name)
            repo.save_structured_resume(sr)
            
            # Save global preferences as fallback
            for k, v in parsed.preferences.items():
                pref = Preference(key=k, value=v)
                repo.save_preference(pref)
                
            # Set this new one as active
            repo.set_active_structured_resume(str(sr.id))

        def finish_and_refresh() -> None:
            self._text_area.clear()
            self._refresh_profiles()

        steps = [
            ("CHECKING OLLAMA AVAILABILITY...", check_ollama_availability),
            ("CONNECTING TO OLLAMA SERVER...", check_and_boot_server),
            ("VERIFYING AI MODEL...", verify_ai_model),
            ("PARSING MASTER RESUME STRUCTURE...", parse_resume),
            ("SAVING PREFERENCES AND VECTORS...", save_data)
        ]
        
        # Connect the all_completed signal to our refresh function
        original_start = self._loader.start_sequence
        def wrapped_start(steps_list):
            original_start(steps_list)
            try:
                self._loader._task.all_completed.disconnect(finish_and_refresh)
            except Exception:
                pass
            self._loader._task.all_completed.connect(finish_and_refresh)
            
        wrapped_start(steps)
