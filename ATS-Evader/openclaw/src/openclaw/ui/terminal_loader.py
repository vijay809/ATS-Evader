"""Reusable Terminal Loader Overlay."""
from __future__ import annotations

from typing import Callable, Any
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QProgressBar, QFrame, QScrollArea, QPushButton
)


class LoaderTask(QThread):
    """Executes a series of steps in a background thread."""
    step_started = Signal(str)
    step_completed = Signal(str)
    step_failed = Signal(str, str)
    all_completed = Signal()

    def __init__(self, steps: list[tuple[str, Callable[[], Any]]]) -> None:
        super().__init__()
        self._steps = steps

    def run(self) -> None:
        for name, func in self._steps:
            self.step_started.emit(name)
            try:
                func()
                self.step_completed.emit(name)
            except Exception as e:
                self.step_failed.emit(name, str(e))
                return  # Stop execution on failure
        self.all_completed.emit()


class TerminalLoaderOverlay(QFrame):
    """An overlay widget that displays a terminal-like sequence of events."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.hide()
        
        # Transparent background for the overlay
        self.setStyleSheet("TerminalLoaderOverlay { background-color: rgba(19, 19, 19, 0.95); }")
        
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Container to limit width and height
        container = QFrame()
        container.setFixedSize(600, 400)
        container.setStyleSheet("background-color: transparent; border: none;")
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(24)

        # Terminal Window
        term_frame = QFrame()
        term_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(10, 10, 10, 0.9);
                border: 1px solid rgba(236, 178, 255, 0.15);
                border-radius: 8px;
            }
        """)
        term_layout = QVBoxLayout(term_frame)
        term_layout.setContentsMargins(0, 0, 0, 0)
        term_layout.setSpacing(0)

        # Terminal Header
        header = QFrame()
        header.setFixedHeight(32)
        header.setStyleSheet("background-color: rgba(42, 42, 42, 0.8); border-bottom: 1px solid rgba(255,255,255,0.05); border-radius: 8px; border-bottom-left-radius: 0; border-bottom-right-radius: 0;")
        header_layout = QHBoxLayout(header)
        title = QLabel("Loading...")
        title.setStyleSheet("color: rgba(193, 198, 215, 0.7); font-family: monospace; font-size: 12px; font-weight: bold; border: none;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(title)
        term_layout.addWidget(header)

        # Terminal Body
        self._term_body = QScrollArea()
        self._term_body.setWidgetResizable(True)
        self._term_body.setFixedHeight(256)
        self._term_body.setStyleSheet("border: none; background: transparent;")
        
        self._log_container = QWidget()
        self._log_container.setStyleSheet("background: transparent;")
        self._log_layout = QVBoxLayout(self._log_container)
        self._log_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._log_layout.setContentsMargins(16, 16, 16, 16)
        self._log_layout.setSpacing(8)
        
        self._term_body.setWidget(self._log_container)
        term_layout.addWidget(self._term_body)

        container_layout.addWidget(term_frame)

        # Progress Section
        prog_layout = QHBoxLayout()
        prog_lbl = QLabel("PARSING SEQUENCE")
        prog_lbl.setStyleSheet("color: #adc6ff; font-family: monospace; font-size: 12px; font-weight: bold; border: none;")
        self._prog_pct = QLabel("0%")
        self._prog_pct.setStyleSheet("color: white; font-family: monospace; font-size: 14px; font-weight: bold; border: none;")
        prog_layout.addWidget(prog_lbl)
        prog_layout.addStretch()
        prog_layout.addWidget(self._prog_pct)
        
        container_layout.addLayout(prog_layout)

        self._progress = QProgressBar()
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(6)
        self._progress.setStyleSheet("""
            QProgressBar {
                background-color: #2a2a2a;
                border: none;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background-color: #adc6ff;
                border-radius: 3px;
            }
        """)
        container_layout.addWidget(self._progress)

        # Close Button
        self._close_btn = QPushButton("Close")
        self._close_btn.setMinimumHeight(40)
        self._close_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2a2a; color: white; 
                border-radius: 6px; font-weight: bold; font-family: monospace;
            }
            QPushButton:hover { background-color: #353534; }
        """)
        self._close_btn.clicked.connect(self.hide)
        self._close_btn.hide()
        container_layout.addWidget(self._close_btn)

        layout.addWidget(container)
        
        self._task: LoaderTask | None = None
        self._total_steps = 0
        self._current_step = 0
        
        self._current_pct = 0
        
        self._dots_timer = QTimer(self)
        self._dots_timer.setInterval(500)
        self._dots_timer.timeout.connect(self._update_dots)
        self._dots_label: QLabel | None = None

    def start_sequence(self, steps: list[tuple[str, Callable[[], Any]]]) -> None:
        """Starts the terminal loader with a given sequence of steps."""
        if self.parent():
            self.setGeometry(0, 0, self.parent().width(), self.parent().height())
        self.show()
        self.raise_()
        self._close_btn.hide()
        
        # Clear logs
        while self._log_layout.count():
            child = self._log_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
                
        self._total_steps = len(steps)
        self._current_step = 0
        
        self._current_pct = 0
        self._prog_pct.setText("0%")
        self._progress.setValue(0)
        self._schedule_next_jump()
        
        self._task = LoaderTask(steps)
        self._task.step_started.connect(self._on_step_started)
        self._task.step_completed.connect(self._on_step_completed)
        self._task.step_failed.connect(self._on_step_failed)
        self._task.all_completed.connect(self._on_all_completed)
        self._task.start()

    def _update_dots(self) -> None:
        if self._dots_label:
            text = self._dots_label.text()
            if len(text) > 10:
                self._dots_label.setText(".")
            else:
                self._dots_label.setText(text + " .")

    def _append_log(self, status: str, text: str, is_error: bool = False, is_busy: bool = False) -> None:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        class CopyLabel(QLabel):
            def __init__(self, status_text: str, copy_text: str) -> None:
                super().__init__(status_text)
                self.copy_text = copy_text
            def mousePressEvent(self, event: Any) -> None:
                from PySide6.QtGui import QGuiApplication
                QGuiApplication.clipboard().setText(self.copy_text)
                super().mousePressEvent(event)

        if is_error:
            status_lbl = CopyLabel(f"[{status}]", text)
            status_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            status_lbl = QLabel(f"[{status}]")
        status_lbl.setFixedWidth(80)
        
        if is_error:
            status_lbl.setStyleSheet("color: #ffb4ab; font-family: monospace; font-size: 9px; font-weight: bold; border: none;")
        elif is_busy:
            status_lbl.setStyleSheet("color: #ffb595; font-family: monospace; font-size: 9px; font-weight: bold; border: none;")
        else:
            status_lbl.setStyleSheet("color: #adc6ff; font-family: monospace; font-size: 9px; font-weight: bold; border: none;")
            
        text_lbl = QLabel(text)
        # text_lbl.setWordWrap(True)
        text_lbl.setStyleSheet("color: #e5e2e1; font-family: monospace; font-size: 9px; border: none;")
        
        row_layout.addWidget(status_lbl)
        row_layout.addWidget(text_lbl)
        self._log_layout.addWidget(row)
        
        # Scroll to bottom
        self._term_body.verticalScrollBar().setValue(self._term_body.verticalScrollBar().maximum())

    def _on_step_started(self, name: str) -> None:
        self._append_log("BUSY", name, is_busy=True)
        
        # Add dots line
        self._dots_label = QLabel(".")
        self._dots_label.setStyleSheet("color: #adc6ff; font-family: monospace; font-size: 9px; font-weight: bold; padding-left: 80px; border: none;")
        self._log_layout.addWidget(self._dots_label)
        self._dots_timer.start()

    def _on_step_completed(self, name: str) -> None:
        self._dots_timer.stop()
        if self._dots_label:
            self._dots_label.deleteLater()
            self._dots_label = None
            
        self._append_log(" OK ", f"{name} completed.")
        self._current_step += 1

    def _on_step_failed(self, name: str, error: str) -> None:
        self._dots_timer.stop()
        if self._dots_label:
            self._dots_label.deleteLater()
            self._dots_label = None
            
        self._append_log("ERROR", f"{name} FAILED: {error}", is_error=True)
        self._close_btn.show()

    def _on_all_completed(self) -> None:
        self._dots_timer.stop()
        if self._dots_label:
            self._dots_label.deleteLater()
            self._dots_label = None
            
        self._append_log("SUCCESS", "SEQUENCE COMPLETED SUCCESSFULLY.")
        self._prog_pct.setText("100%")
        self._progress.setValue(100)
        self._current_pct = 100
        self._close_btn.show()

    def _schedule_next_jump(self) -> None:
        if self._current_pct >= 90:
            return
        if self._task is None or not self._task.isRunning():
            return
        import random
        # Random interval under 10 seconds (e.g. 1s to 9s)
        delay_ms = random.randint(1000, 9000)
        QTimer.singleShot(delay_ms, self._on_progress_jump)

    def _on_progress_jump(self) -> None:
        if self._current_pct >= 90:
            return
        if self._task is None or not self._task.isRunning():
            return
        
        import random
        # Random percentage jump under 10
        jump = random.randint(1, 9)
        self._current_pct += jump
        if self._current_pct > 90:
            self._current_pct = 90
            
        self._prog_pct.setText(f"{self._current_pct}%")
        self._progress.setValue(self._current_pct)
        self._schedule_next_jump()

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        # Resize to cover parent
        if self.parent():
            self.resize(self.parent().size())
