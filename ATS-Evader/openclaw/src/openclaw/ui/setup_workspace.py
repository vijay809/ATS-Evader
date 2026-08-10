"""Setup workspace matching the Stitch AI design."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPlainTextEdit, QPushButton, QMessageBox
)

from openclaw.core.documents import StructuredResume, Preference
from openclaw.plugins.ats import ATS_ANALYZER_SERVICE, AtsAnalyzer, ParsedResumeData

if TYPE_CHECKING:
    from openclaw.core.runtime import Runtime


from openclaw.ui.terminal_loader import TerminalLoaderOverlay

class SetupWorkspace(QWidget):
    """The Setup screen for parsing a master resume."""

    def __init__(self, runtime: 'Runtime') -> None:
        super().__init__()
        self._runtime = runtime
        
        self._loader = TerminalLoaderOverlay(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)

        # Header
        header = QLabel("System Setup")
        header.setStyleSheet("font-size: 32px; font-weight: 600; color: #e5e2e1;")
        
        desc = QLabel("Initialize the AI matching engine by providing a comprehensive master resume.")
        desc.setStyleSheet("font-size: 16px; color: #c1c6d7;")
        desc.setWordWrap(True)

        layout.addWidget(header)
        layout.addWidget(desc)

        # Main Input Area
        self._text_area = QPlainTextEdit()
        self._text_area.setPlaceholderText("Paste master resume, core job description, or structural requirements here...")
        # Styling via global QSS later, but adding some basics here
        self._text_area.setStyleSheet("background-color: #080808; color: #e5e2e1; padding: 16px; border-radius: 8px;")
        
        layout.addWidget(self._text_area, stretch=1)

        # Buttons
        btn_layout = QHBoxLayout()
        self._clear_btn = QPushButton("Clear")
        self._clear_btn.clicked.connect(self._text_area.clear)
        
        self._parse_btn = QPushButton("Parse & Extract Details")
        self._parse_btn.setMinimumHeight(56)
        self._parse_btn.setStyleSheet("background-color: #005bc1; color: white; border-radius: 12px; font-size: 20px; font-weight: bold;")
        self._parse_btn.clicked.connect(self._on_parse)
        
        btn_layout.addWidget(self._clear_btn)
        btn_layout.addWidget(self._parse_btn, stretch=1)
        layout.addLayout(btn_layout)

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
            # Synchronous call, runs in LoaderTask thread
            result = analyzer_typed.parse_master_resume(text, model)
            state['result'] = result

        def save_data() -> None:
            result = state.get('result')
            if not result or not hasattr(result, "preferences"):
                raise Exception("Invalid parsed data.")
            
            parsed = typing.cast(ParsedResumeData, result)
            sr = StructuredResume(raw_content=text, parsed_json=parsed.structured_json)
            self._runtime.plugins._context.documents.save_structured_resume(sr)
            for k, v in parsed.preferences.items():
                pref = Preference(key=k, value=v)
                self._runtime.plugins._context.documents.save_preference(pref)

        steps = [
            ("CHECKING OLLAMA AVAILABILITY...", check_ollama_availability),
            ("CONNECTING TO OLLAMA SERVER...", check_and_boot_server),
            ("VERIFYING AI MODEL...", verify_ai_model),
            ("PARSING MASTER RESUME STRUCTURE...", parse_resume),
            ("SAVING PREFERENCES AND VECTORS...", save_data)
        ]
        
        self._loader.start_sequence(steps)
