"""Desktop shell and monitoring surface for the local runtime."""

from __future__ import annotations

import asyncio
from datetime import UTC
from uuid import UUID

from PySide6.QtCore import Qt, QSize, QTimer, Signal
from PySide6.QtGui import QIcon, QAction
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from openclaw.core.events import RuntimeEvent
from openclaw.core.runtime import Runtime
from openclaw.core.tasks import TaskStatus
from openclaw.ui.ai_workspace import AiWorkspace
from openclaw.ui.setup_workspace import SetupWorkspace
from openclaw.ui.process_workspace import ProcessWorkspace
from openclaw.ui.job_pipeline_workspace import JobPipelineWorkspace
from openclaw.ui.monitor import task_rows


class MainWindow(QMainWindow):
    """Read-only monitoring UI; task execution remains owned by the runtime."""

    event_received = Signal(object)

    def __init__(self, runtime: Runtime) -> None:
        super().__init__()
        self._runtime = runtime
        self.setWindowTitle("OpenClaw")
        self.setMinimumSize(1000, 650)

        # Central Widget Layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        central_layout = QHBoxLayout(central_widget)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        # -- LEFT NAVIGATION RAIL --
        nav_rail = QFrame()
        nav_rail.setFixedWidth(80)
        nav_rail.setStyleSheet("background-color: #131313; border-right: 1px solid rgba(255,255,255,0.05);")
        nav_layout = QVBoxLayout(nav_rail)
        nav_layout.setContentsMargins(0, 24, 0, 24)
        nav_layout.setSpacing(32)

        # Temporary Logo Placeholder
        logo = QLabel("OC")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet("color: #adc6ff; font-weight: bold; font-size: 24px; border: none;")
        nav_layout.addWidget(logo)

        # Nav Buttons
        def create_nav_btn(text: str) -> QPushButton:
            btn = QPushButton(text)
            btn.setFixedSize(80, 60)
            btn.setStyleSheet("""
                QPushButton {
                    background: transparent; color: #8b90a0; 
                    border: none; font-size: 10px; font-weight: bold;
                }
                QPushButton:checked {
                    color: #ecb2ff; border-left: 2px solid #ecb2ff;
                }
            """)
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            return btn

        self._btn_setup = create_nav_btn("SETUP")
        self._btn_process = create_nav_btn("PROCESS")
        self._btn_history = create_nav_btn("HISTORY")
        self._btn_setup.setChecked(True)

        nav_layout.addWidget(self._btn_setup)
        nav_layout.addWidget(self._btn_process)
        nav_layout.addWidget(self._btn_history)
        nav_layout.addStretch()

        # -- RIGHT MAIN AREA --
        right_area = QWidget()
        right_layout = QVBoxLayout(right_area)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Top Bar
        top_bar = QFrame()
        top_bar.setFixedHeight(64)
        top_bar.setStyleSheet("background-color: rgba(19, 19, 19, 0.9); border-bottom: 1px solid rgba(255,255,255,0.05);")
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(24, 0, 24, 0)

        status_lbl = QLabel("System Active")
        status_lbl.setStyleSheet("color: #c1c6d7; font-size: 12px; font-weight: bold; text-transform: uppercase; border: none;")
        top_bar_layout.addWidget(status_lbl)
        top_bar_layout.addStretch()

        right_layout.addWidget(top_bar)

        # Stacked Workspaces
        self._setup = SetupWorkspace(runtime)
        self._process = ProcessWorkspace(runtime)
        self._history = JobPipelineWorkspace(runtime)

        self._stacked = QStackedWidget()
        self._stacked.addWidget(self._setup)
        self._stacked.addWidget(self._process)
        self._stacked.addWidget(self._history)
        right_layout.addWidget(self._stacked)

        central_layout.addWidget(nav_rail)
        central_layout.addWidget(right_area)

        # Connections
        self._btn_setup.clicked.connect(lambda: self._stacked.setCurrentIndex(0))
        self._btn_process.clicked.connect(lambda: self._stacked.setCurrentIndex(1))
        self._btn_history.clicked.connect(lambda: self._stacked.setCurrentIndex(2))

    async def _on_task_changed(self, event: RuntimeEvent) -> None:
        self.event_received.emit(event)
