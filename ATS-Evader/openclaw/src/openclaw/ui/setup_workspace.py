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


class ParseWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, analyzer: AtsAnalyzer, raw_text: str, model: str):
        super().__init__()
        self._analyzer = analyzer
        self._raw_text = raw_text
        self._model = model

    def run() -> None:
        try:
            result = self._analyzer.parse_master_resume(self._raw_text, self._model)
            self.completed.emit(result)
        except Exception as e:
            self.failed.emit(str(e))


class SetupWorkspace(QWidget):
    """The Setup screen for parsing a master resume."""

    def __init__(self, runtime: 'Runtime') -> None:
        super().__init__()
        self._runtime = runtime
        self._worker: ParseWorker | None = None

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

        self._parse_btn.setText("Analyzing Syntax...")
        self._parse_btn.setEnabled(False)

        # Safe cast
        import typing
        from openclaw.plugins.ats import AtsAnalyzer
        analyzer_typed = typing.cast(AtsAnalyzer, analyzer)

        self._worker = ParseWorker(analyzer_typed, text, "gemma4:12b")
        self._worker.completed.connect(self._on_parse_complete)
        self._worker.failed.connect(self._on_parse_failed)
        self._worker.start()

    def _on_parse_complete(self, result: object) -> None:
        self._parse_btn.setText("Parse & Extract Details")
        self._parse_btn.setEnabled(True)
        
        if not hasattr(result, "preferences"):
            return
            
        parsed = typing.cast(ParsedResumeData, result) # type: ignore

        # Save Structured Resume
        sr = StructuredResume(raw_content=self._text_area.toPlainText(), parsed_json=parsed.structured_json)
        self._runtime.plugins._context.documents.save_structured_resume(sr)

        # Save Preferences
        for k, v in parsed.preferences.items():
            pref = Preference(key=k, value=v)
            self._runtime.plugins._context.documents.save_preference(pref)

        QMessageBox.information(self, "Success", "Resume parsed and preferences saved successfully!")

    def _on_parse_failed(self, error: str) -> None:
        self._parse_btn.setText("Parse & Extract Details")
        self._parse_btn.setEnabled(True)
        QMessageBox.critical(self, "Error", f"Failed to parse resume: {error}")
