"""Setup workspace matching the Stitch AI design."""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from openclaw.core.documents import Preference, StructuredResume
from openclaw.plugins.ats import ATS_ANALYZER_SERVICE, AtsAnalyzer, ParsedResumeData

if TYPE_CHECKING:
    from openclaw.core.runtime import Runtime


from openclaw.ui.terminal_loader import TerminalLoaderOverlay


class HistoryProfileWidget(QFrame):
    """Expandable accordion for historical profiles."""
    def __init__(self, resume: StructuredResume, on_set_active: Callable[[str], None], on_delete: Callable[[str], None]) -> None:
        super().__init__()
        self.resume = resume
        self.on_set_active = on_set_active
        self.on_delete = on_delete
        self.is_expanded = False
        
        self.setStyleSheet("""
            HistoryProfileWidget {
                background-color: #ffffff;
                border: 1px solid rgba(139, 126, 200, 0.18);
                border-radius: 10px;
            }
            HistoryProfileWidget:hover {
                border-color: rgba(139, 126, 200, 0.35);
                background-color: #fcfcff;
            }
        """)
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(16, 14, 16, 14)
        self.main_layout.setSpacing(10)
        
        # Header (Always visible)
        self.header_widget = QWidget()
        header_layout = QHBoxLayout(self.header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        name_lbl = QLabel(resume.name)
        name_lbl.setStyleSheet("color: #141c29; font-size: 14px; font-weight: 700; border: none;")
        
        # Parse some basic info from JSON
        role = "Historical Resume"
        try:
            import json
            parsed = json.loads(resume.parsed_json)
            if isinstance(parsed, dict) and "preferences" in parsed:
                role = parsed["preferences"].get("Target Role", "Historical Resume")
        except Exception:
            pass
            
        time_str = datetime.fromtimestamp(resume.created_at, tz=UTC).strftime("%b %d, %H:%M")
        sub_lbl = QLabel(f"{time_str} • {role}")
        sub_lbl.setStyleSheet("color: #8f96a8; font-size: 12px; font-weight: 500; border: none;")
        
        info_layout.addWidget(name_lbl)
        info_layout.addWidget(sub_lbl)
        
        self.expand_icon = QLabel("▼")
        self.expand_icon.setStyleSheet("color: #8b7ec8; font-size: 12px; font-weight: bold; border: none;")
        
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
        actions_layout.setSpacing(8)
        
        set_active_btn = QPushButton("Set as Active Profile")
        set_active_btn.setStyleSheet("""
            QPushButton {
                background-color: #e8e4f7;
                border: 1px solid rgba(94, 82, 152, 0.3);
                color: #5e5298;
                border-radius: 6px;
                padding: 7px 14px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #ddd7f3; }
        """)
        set_active_btn.clicked.connect(lambda: self.on_set_active(str(self.resume.id)))
        
        delete_btn = QPushButton("Delete")
        delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffdad6;
                border: 1px solid rgba(142, 69, 85, 0.3);
                color: #591b28;
                border-radius: 6px;
                padding: 7px 14px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #f4a8b8; }
        """)
        delete_btn.clicked.connect(lambda: self.on_delete(str(self.resume.id)))
        
        actions_layout.addWidget(set_active_btn)
        actions_layout.addWidget(delete_btn)
        actions_layout.addStretch()
        
        details_layout.addLayout(actions_layout)
        
        self.details_widget.hide()
        self.main_layout.addWidget(self.details_widget)
        
    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_expanded = not self.is_expanded
            if self.is_expanded:
                self.details_widget.show()
                self.expand_icon.setText("▲")
            else:
                self.details_widget.hide()
                self.expand_icon.setText("▼")


class ResumeDropZone(QFrame):
    file_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._default_style = """
            ResumeDropZone {
                background-color: #ffffff;
                border: 1.5px dashed rgba(139, 126, 200, 0.45);
                border-radius: 12px;
            }
            ResumeDropZone:hover {
                background-color: #fcfcff;
                border-color: #8b7ec8;
            }
        """
        self._hover_style = """
            ResumeDropZone {
                background-color: #f4f2fb;
                border: 2px dashed #5e5298;
                border-radius: 12px;
            }
        """
        self.setStyleSheet(self._default_style)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(16)

        icon = QLabel("📄")
        icon.setStyleSheet("font-size: 26px; border: none; background: transparent;")

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        title = QLabel("Import Master Resume (PDF, DOCX, TXT)")
        title.setStyleSheet("color: #141c29; font-weight: 700; font-size: 13px; border: none; background: transparent;")
        subtitle = QLabel("Drag & drop your document here, or click Browse Files to select")
        subtitle.setStyleSheet("color: #8f96a8; font-size: 11px; border: none; background: transparent;")
        text_layout.addWidget(title)
        text_layout.addWidget(subtitle)

        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet("color: #186a59; font-size: 11px; font-weight: 700; border: none; background: transparent;")

        browse_btn = QPushButton("Browse Files")
        browse_btn.setStyleSheet("""
            QPushButton {
                background-color: #e8e4f7;
                color: #5e5298;
                border: 1px solid rgba(94, 82, 152, 0.3);
                border-radius: 8px;
                padding: 7px 16px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #ddd7f3;
            }
        """)
        browse_btn.clicked.connect(self._open_file_dialog)

        layout.addWidget(icon)
        layout.addLayout(text_layout, stretch=1)
        layout.addWidget(self.status_lbl)
        layout.addWidget(browse_btn)

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._open_file_dialog()

    def _open_file_dialog(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Resume Document",
            "",
            "Resume Files (*.pdf *.docx *.txt *.md);;PDF Files (*.pdf);;Word Documents (*.docx);;All Files (*)",
        )
        if file_path:
            self.file_selected.emit(file_path)

    def dragEnterEvent(self, event: Any) -> None:
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                path = urls[0].toLocalFile().lower()
                if any(path.endswith(ext) for ext in [".pdf", ".docx", ".txt", ".md"]):
                    self.setStyleSheet(self._hover_style)
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dragLeaveEvent(self, event: Any) -> None:
        self.setStyleSheet(self._default_style)

    def dropEvent(self, event: Any) -> None:
        self.setStyleSheet(self._default_style)
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                file_path = urls[0].toLocalFile()
                if any(file_path.lower().endswith(ext) for ext in [".pdf", ".docx", ".txt", ".md"]):
                    self.file_selected.emit(file_path)
                    event.acceptProposedAction()
                    return
        event.ignore()


class SetupWorkspace(QWidget):
    """The Setup screen for parsing a master resume."""

    def __init__(self, runtime: Runtime) -> None:
        super().__init__()
        self._runtime = runtime
        
        self._loader = TerminalLoaderOverlay(self)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                background: #f7f8fc;
                width: 8px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #d8daf0;
                min-height: 24px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: #8b7ec8;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Header
        header = QLabel("System Setup")
        header.setStyleSheet("font-size: 26px; font-weight: 700; color: #141c29; border: none;")
        
        desc = QLabel("Initialize the AI matching engine by uploading or providing a comprehensive master resume.")
        desc.setStyleSheet("font-size: 14px; color: #5c6479; border: none;")
        desc.setWordWrap(True)

        layout.addWidget(header)
        layout.addWidget(desc)

        # File Drop Zone
        self._drop_zone = ResumeDropZone(self)
        self._drop_zone.file_selected.connect(self._on_file_loaded)
        layout.addWidget(self._drop_zone)

        # Main Input Area
        self._text_area = QPlainTextEdit()
        self._text_area.setPlaceholderText("Or paste master resume text directly here...")
        self._text_area.setMinimumHeight(200)
        self._text_area.setStyleSheet("""
            QPlainTextEdit {
                background-color: #ffffff;
                color: #141c29;
                border: 1px solid rgba(139, 126, 200, 0.25);
                border-radius: 10px;
                padding: 14px;
                font-size: 13px;
                selection-background-color: #e8e4f7;
                selection-color: #141c29;
            }
            QPlainTextEdit:focus {
                border-color: #8b7ec8;
            }
        """)
        
        layout.addWidget(self._text_area)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.clicked.connect(self._text_area.clear)
        self._clear_btn.setStyleSheet("""
            QPushButton { 
                background-color: #ffffff; 
                color: #5c6479; 
                border: 1px solid rgba(143, 150, 168, 0.35);
                border-radius: 10px; 
                padding: 12px 24px; 
                font-weight: 600; 
                font-size: 13px;
            }
            QPushButton:hover { 
                background-color: #f7f8fc; 
                color: #141c29;
            }
        """)
        
        self._parse_btn = QPushButton("Parse & Extract Details")
        self._parse_btn.setMinimumHeight(44)
        self._parse_btn.setStyleSheet("""
            QPushButton {
                background-color: #8b7ec8; 
                color: white; 
                border: none;
                border-radius: 10px; 
                font-size: 14px; 
                font-weight: 700;
                padding: 12px 24px;
            }
            QPushButton:hover {
                background-color: #5e5298;
            }
        """)
        self._parse_btn.clicked.connect(self._on_parse)
        
        btn_layout.addWidget(self._clear_btn)
        btn_layout.addWidget(self._parse_btn, stretch=1)
        layout.addLayout(btn_layout)

        # Profiles Section
        self._profiles_container = QWidget()
        self._profiles_layout = QVBoxLayout(self._profiles_container)
        self._profiles_layout.setContentsMargins(0, 12, 0, 0)
        self._profiles_layout.setSpacing(20)
        layout.addWidget(self._profiles_container)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._refresh_profiles()

    def _refresh_profiles(self) -> None:
        # Clear layout
        while self._profiles_layout.count():
            item = self._profiles_layout.takeAt(0)
            if item is not None:
                w = item.widget()
                if w is not None:
                    w.setParent(None)
                    w.deleteLater()
                
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
                background-color: #ffffff;
                border: 1px solid rgba(139, 126, 200, 0.25);
                border-radius: 14px;
            }
        """)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        
        header_layout = QHBoxLayout()
        icon = QLabel("👤")
        icon.setStyleSheet("border: none; background: transparent; font-size: 16px;")
        title = QLabel("CURRENTLY ACTIVE PROFILE")
        title.setStyleSheet("""
            background-color: #e1f5ef;
            color: #186a59;
            font-size: 11px;
            font-weight: 700;
            padding: 3px 10px;
            border-radius: 8px;
            border: 1px solid rgba(24, 106, 89, 0.2);
        """)
        header_layout.addWidget(icon)
        header_layout.addWidget(title)
        header_layout.addStretch()
        layout.addLayout(header_layout)
        
        info_layout = QHBoxLayout()
        name_lbl = QLabel(resume.name)
        name_lbl.setStyleSheet("color: #141c29; font-size: 22px; font-weight: 700; border: none;")
        
        role_lbl = QLabel(role)
        role_lbl.setStyleSheet("""
            color: #5e5298; 
            font-size: 13px; 
            font-weight: 600; 
            border: none; 
            padding: 4px 10px; 
            background-color: #e8e4f7; 
            border-radius: 8px;
        """)
        
        info_layout.addWidget(name_lbl)
        info_layout.addSpacing(10)
        info_layout.addWidget(role_lbl)
        info_layout.addStretch()
        layout.addLayout(info_layout)
        
        self._profiles_layout.addWidget(container)

    def _build_history(self, history: list[StructuredResume]) -> None:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        
        header_layout = QHBoxLayout()
        title = QLabel("RECENT HISTORY")
        title.setStyleSheet("color: #8f96a8; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; border: none;")
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

    def _on_file_loaded(self, file_path: str) -> None:
        try:
            import typing

            from openclaw.plugins.documents import DocumentIngestionService

            try:
                ingest_service = self._runtime.services.get("documents.ingestion")
            except LookupError:
                ingest_service = DocumentIngestionService()

            ingestion_typed = typing.cast(DocumentIngestionService, ingest_service)
            text = ingestion_typed.read_text(file_path)
            self._text_area.setPlainText(text)
            file_name = Path(file_path).name
            self._drop_zone.status_lbl.setText(f"✓ Loaded: {file_name}")
        except Exception as e:
            QMessageBox.warning(self, "Document Load Error", f"Failed to extract text from {file_path}: {e}")

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

        from openclaw.plugins.ollama import OLLAMA_CLIENT_SERVICE, OllamaClient
        
        analyzer_typed = typing.cast(AtsAnalyzer, analyzer)
        try:
            ollama = typing.cast(OllamaClient, self._runtime.services.get(OLLAMA_CLIENT_SERVICE))
        except LookupError:
            QMessageBox.warning(self, "Error", "Ollama service not available.")
            return

        state: dict[str, Any] = {}

        def check_ollama_availability() -> None:
            if not ollama.check_ollama_availability():
                raise RuntimeError("Ollama executable not found in system PATH. Please install Ollama.")

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
                raise RuntimeError("Started Ollama but it did not become ready within 10 seconds.")

        def verify_ai_model() -> None:
            models = ollama.get_available_models()
            if not models:
                raise RuntimeError("No AI models installed in local Ollama.")
            curr_model = state.get("model")
            if not isinstance(curr_model, str) or curr_model not in models:
                state["model"] = models[0]

        def parse_resume() -> None:
            model = state.get("model")
            model_str = model if isinstance(model, str) else None
            result = analyzer_typed.parse_master_resume(text, model_str)
            state["result"] = result

        def save_data() -> None:
            result = state.get("result")
            if not isinstance(result, ParsedResumeData):
                raise RuntimeError("Invalid parsed data.")
            
            candidate_name = result.preferences.get("Candidate Name", "Master Resume")
            
            repo = self._runtime.plugins._context.documents
            # Store the entire ParsedResumeData payload so preferences move with the resume
            sr = StructuredResume(raw_content=text, parsed_json=result.model_dump_json(), name=candidate_name)
            repo.save_structured_resume(sr)
            
            # Save global preferences as fallback
            for k, v in result.preferences.items():
                pref = Preference(key=k, value=v)
                repo.save_preference(pref)
                
            # Set this new one as active
            repo.set_active_structured_resume(str(sr.id))

        def finish_and_refresh() -> None:
            self._text_area.clear()
            self._refresh_profiles()

        steps: list[tuple[str, Callable[[], None]]] = [
            ("CHECKING OLLAMA AVAILABILITY...", check_ollama_availability),
            ("CONNECTING TO OLLAMA SERVER...", check_and_boot_server),
            ("VERIFYING AI MODEL...", verify_ai_model),
            ("PARSING MASTER RESUME STRUCTURE...", parse_resume),
            ("SAVING PREFERENCES AND VECTORS...", save_data)
        ]
        
        # Connect the all_completed signal to our refresh function
        def wrapped_start(steps_list: list[tuple[str, Callable[[], None]]]) -> None:
            self._loader.start_sequence(steps_list)
            task = self._loader._task
            if task is not None:
                task.all_completed.connect(finish_and_refresh)
            
        wrapped_start(steps)
