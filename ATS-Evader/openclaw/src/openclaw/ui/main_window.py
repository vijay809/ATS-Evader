"""Desktop shell and monitoring surface for the local runtime."""

from __future__ import annotations

import asyncio
from datetime import UTC
from uuid import UUID

from PySide6.QtCore import Qt, QSize, QTimer, Signal, QThread
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
    QProgressBar,
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

class SystemMonitorThread(QThread):
    metrics_updated = Signal(float, float, float, float)  # cpu, ram, gpu_load, vram_usage
    
    def run(self) -> None:
        import time
        import psutil
        import subprocess

        # Find nvidia-smi bypassing PATH issues
        nvidia_smi_path = None
        for path in [
            "nvidia-smi",
            r"C:\Windows\System32\nvidia-smi.exe",
            r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"
        ]:
            try:
                subprocess.run([path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                nvidia_smi_path = path
                break
            except FileNotFoundError:
                continue

        while not self.isInterruptionRequested():
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent
            gpu_load = 0.0
            vram_usage = 0.0
            
            if nvidia_smi_path:
                try:
                    creationflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
                    result = subprocess.run(
                        [nvidia_smi_path, "--query-gpu=utilization.gpu,memory.used,memory.total", "--format=csv,noheader,nounits"],
                        capture_output=True, text=True, creationflags=creationflags
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        parts = result.stdout.strip().split(',')
                        if len(parts) >= 3:
                            gpu_load = float(parts[0].strip())
                            used_mem = float(parts[1].strip())
                            total_mem = float(parts[2].strip())
                            vram_usage = (used_mem / total_mem) * 100 if total_mem > 0 else 0.0
                except Exception:
                    pass
            
            self.metrics_updated.emit(cpu, ram, gpu_load, vram_usage)
            time.sleep(1.5)


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

        top_bar_vlayout = QVBoxLayout()
        top_bar_vlayout.setSpacing(4)
        
        self._status_lbl = QLabel("[ ] System Active    [ ] Ollama server    [ ] AI [None]")
        self._status_lbl.setStyleSheet("color: #e5e2e1; font-size: 13px; font-weight: bold; border: none;")
        
        self._info_lbl = QLabel("Initializing system checks...")
        self._info_lbl.setStyleSheet("color: #8b90a0; font-size: 11px; border: none;")
        
        top_bar_vlayout.addWidget(self._status_lbl)
        top_bar_vlayout.addWidget(self._info_lbl)
        
        top_bar_layout.addLayout(top_bar_vlayout)
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

        # Bottom Bar for System Metrics
        bottom_bar = QFrame()
        bottom_bar.setFixedHeight(40)
        bottom_bar.setStyleSheet("background-color: rgba(19, 19, 19, 0.9); border-top: 1px solid rgba(255,255,255,0.05);")
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(24, 0, 24, 0)
        bottom_layout.setSpacing(24)

        def create_metric_widget(label_text: str) -> QWidget:
            container = QWidget()
            layout = QHBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(12)
            
            lbl = QLabel(f"{label_text} 0%")
            lbl.setFixedWidth(65)
            lbl.setStyleSheet("color: #8b90a0; font-size: 11px; font-weight: bold; border: none;")
            
            pb = QProgressBar()
            pb.setTextVisible(False)
            pb.setFixedHeight(12)
            pb.setStyleSheet("""
                QProgressBar {
                    background-color: #2a2a2a; border-radius: 4px;
                }
                QProgressBar::chunk {
                    background-color: #adc6ff; border-radius: 4px;
                }
            """)
            
            layout.addWidget(lbl)
            layout.addWidget(pb, stretch=1)
            
            # Store references to update later
            container.pb = pb
            container.lbl = lbl
            container.label_prefix = label_text
            return container

        self._cpu_widget = create_metric_widget("CPU")
        self._ram_widget = create_metric_widget("RAM")
        self._gpu_widget = create_metric_widget("GPU")
        self._vram_widget = create_metric_widget("VRAM")

        bottom_layout.addWidget(self._cpu_widget, stretch=1)
        bottom_layout.addWidget(self._ram_widget, stretch=1)
        bottom_layout.addWidget(self._gpu_widget, stretch=1)
        bottom_layout.addWidget(self._vram_widget, stretch=1)

        right_layout.addWidget(bottom_bar)

        central_layout.addWidget(nav_rail)
        central_layout.addWidget(right_area)

        # Start Monitor Thread
        self._monitor_thread = SystemMonitorThread(self)
        self._monitor_thread.metrics_updated.connect(self._update_metrics)
        self._monitor_thread.start()

    def _update_metrics(self, cpu: float, ram: float, gpu: float, vram: float) -> None:
        def update_single_metric(widget: Any, new_val: float) -> None:
            old_val = widget.pb.value()
            int_val = int(new_val)
            widget.pb.setValue(int_val)
            widget.lbl.setText(f"{widget.label_prefix} {int_val}%")
            
            # Highlight jump > 5% (increasing or decreasing)
            if abs(int_val - old_val) > 5:
                widget.pb.setFixedHeight(14)
                widget.pb.setStyleSheet("""
                    QProgressBar {
                        background-color: #2a2a2a; border-radius: 8px;
                    }
                    QProgressBar::chunk {
                        background-color: #ffb595; border-radius: 8px;
                    }
                """)
                
                # Restore original style
                def restore() -> None:
                    widget.pb.setFixedHeight(12)
                    widget.pb.setStyleSheet("""
                        QProgressBar {
                            background-color: #2a2a2a; border-radius: 4px;
                        }
                        QProgressBar::chunk {
                            background-color: #adc6ff; border-radius: 4px;
                        }
                    """)
                from PySide6.QtCore import QTimer
                QTimer.singleShot(2000, restore)

        update_single_metric(self._cpu_widget, cpu)
        update_single_metric(self._ram_widget, ram)
        update_single_metric(self._gpu_widget, gpu)
        update_single_metric(self._vram_widget, vram)

        # Connections
        self._btn_setup.clicked.connect(lambda: self._stacked.setCurrentIndex(0))
        self._btn_process.clicked.connect(lambda: self._stacked.setCurrentIndex(1))
        self._btn_history.clicked.connect(lambda: self._stacked.setCurrentIndex(2))

    def closeEvent(self, event: Any) -> None:
        self._monitor_thread.requestInterruption()
        self._monitor_thread.wait()
        super().closeEvent(event)

    async def _on_task_changed(self, event: RuntimeEvent) -> None:
        self.event_received.emit(event)

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        # Run health check on startup without blocking UI using QThread
        self._run_system_health_check()

    def _run_system_health_check(self) -> None:
        from openclaw.plugins.ollama import OLLAMA_CLIENT_SERVICE, OllamaClient

        try:
            client = self._runtime.services.get(OLLAMA_CLIENT_SERVICE)
        except LookupError:
            self._status_lbl.setText("✓ System Active    ✗ Ollama server    ✗ AI [None]")
            self._info_lbl.setText("Ollama plugin is not loaded.")
            self._info_lbl.setStyleSheet("color: #ffb4ab; font-size: 11px; border: none;")
            return

        import typing
        ollama = typing.cast(OllamaClient, client)

        from PySide6.QtCore import QThread, Signal

        class HealthCheckThread(QThread):
            finished_check = Signal(bool, bool, list)
            
            def __init__(self, ollama_client: OllamaClient, parent: Any = None):
                super().__init__(parent)
                self.ollama = ollama_client
                
            def run(self) -> None:
                has_ollama = self.ollama.check_ollama_availability()
                server_up = False
                models = []
                if has_ollama:
                    try:
                        server_up = self.ollama.check_connection()
                        if server_up:
                            models = self.ollama.get_available_models()
                    except Exception:
                        pass
                self.finished_check.emit(has_ollama, server_up, models)

        self._health_thread = HealthCheckThread(ollama, self)
        self._health_thread.finished_check.connect(self._on_health_check_done)
        self._health_thread.start()

    def _on_health_check_done(self, has_ollama: bool, server_up: bool, models: list[str]) -> None:
        sys_str = "✓"
        ollama_str = "✓" if has_ollama and server_up else ("✗" if not has_ollama else "!")
        
        model_name = "None"
        if models:
            if "gemma4:12b" in models:
                model_name = "gemma4:12b"
            else:
                model_name = models[0]
            ai_str = "✓"
        else:
            ai_str = "✗"

        self._status_lbl.setText(f"{sys_str} System Active    {ollama_str} Ollama server    {ai_str} AI [{model_name}]")

        if not has_ollama:
            self._info_lbl.setText("Ollama is not installed or not in PATH.")
            self._info_lbl.setStyleSheet("color: #ffb4ab; font-size: 11px; border: none;")
        elif not server_up:
            self._info_lbl.setText("Ollama is installed but the server is not running.")
            self._info_lbl.setStyleSheet("color: #ffb595; font-size: 11px; border: none;")
        elif not models:
            self._info_lbl.setText("Ollama server is running, but no AI models are installed.")
            self._info_lbl.setStyleSheet("color: #ffb595; font-size: 11px; border: none;")
        else:
            self._info_lbl.setText(f"System ready. Using model: {model_name}")
            self._info_lbl.setStyleSheet("color: #adc6ff; font-size: 11px; border: none;")
