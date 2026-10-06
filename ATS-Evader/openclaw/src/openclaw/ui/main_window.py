"""Desktop shell and monitoring surface for the local runtime."""

from __future__ import annotations

import logging
import subprocess
import time

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QCloseEvent, QShowEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from openclaw.core.events import RuntimeEvent
from openclaw.core.runtime import Runtime
from openclaw.ui.job_pipeline_workspace import JobPipelineWorkspace
from openclaw.ui.process_workspace import ProcessWorkspace
from openclaw.ui.setup_workspace import SetupWorkspace

logger = logging.getLogger(__name__)


class MetricWidget(QWidget):
    def __init__(self, label_text: str, color: str = "#8b7ec8", track_color: str = "#e8e4f7", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.label_prefix = label_text
        self.color = color
        self.track_color = track_color
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.lbl = QLabel(f"{label_text} 0%")
        self.lbl.setStyleSheet("color: #5c6479; font-family: 'JetBrains Mono', Consolas, monospace; font-size: 11px; font-weight: 600;")

        self.pb = QProgressBar()
        self.pb.setRange(0, 100)
        self.pb.setValue(0)
        self.pb.setTextVisible(False)
        self.pb.setFixedHeight(6)
        self.pb.setStyleSheet(f"""
            QProgressBar {{
                background-color: {self.track_color}; border-radius: 3px; border: none;
            }}
            QProgressBar::chunk {{
                background-color: {self.color}; border-radius: 3px;
            }}
        """)

        layout.addWidget(self.lbl)
        layout.addWidget(self.pb, stretch=1)


class SystemMonitorThread(QThread):
    metrics_updated = Signal(float, float, float, float)  # cpu, ram, gpu_load, vram_usage

    def run(self) -> None:
        import psutil  # type: ignore[import-untyped]

        # Find nvidia-smi bypassing PATH issues
        nvidia_smi_path = None
        for path in [
            "nvidia-smi",
            r"C:\Windows\System32\nvidia-smi.exe",
            r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
        ]:
            try:
                subprocess.run(
                    [path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                nvidia_smi_path = path
                break
            except (FileNotFoundError, OSError):
                continue

        while not self.isInterruptionRequested():
            cpu = float(psutil.cpu_percent())
            ram = float(psutil.virtual_memory().percent)
            gpu_load = 0.0
            vram_usage = 0.0

            if nvidia_smi_path:
                try:
                    creationflags = (
                        subprocess.CREATE_NO_WINDOW
                        if hasattr(subprocess, "CREATE_NO_WINDOW")
                        else 0
                    )
                    result = subprocess.run(
                        [
                            nvidia_smi_path,
                            "--query-gpu=utilization.gpu,memory.used,memory.total",
                            "--format=csv,noheader,nounits",
                        ],
                        capture_output=True,
                        text=True,
                        creationflags=creationflags,
                        check=False,
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        parts = result.stdout.strip().split(",")
                        if len(parts) >= 3:
                            gpu_load = float(parts[0].strip())
                            used_mem = float(parts[1].strip())
                            total_mem = float(parts[2].strip())
                            vram_usage = (
                                (used_mem / total_mem) * 100 if total_mem > 0 else 0.0
                            )
                except (ValueError, OSError) as e:
                    logger.debug("nvidia-smi query failed: %s", e)

            self.metrics_updated.emit(cpu, ram, gpu_load, vram_usage)
            time.sleep(1.5)


class MainWindow(QMainWindow):
    """Read-only monitoring UI; task execution remains owned by the runtime."""

    event_received = Signal(object)

    def __init__(self, runtime: Runtime) -> None:
        super().__init__()
        self._runtime = runtime
        self.setWindowTitle("OpenClaw AI - Autonomous Career Agent & Tailoring Console")
        self.setMinimumSize(1000, 650)

        # Central Widget Layout
        central_widget = QWidget()
        central_widget.setStyleSheet("""
            QWidget {
                background-color: #f7f8fc;
                color: #141c29;
                font-family: 'Plus Jakarta Sans', 'Segoe UI', -apple-system, sans-serif;
            }
        """)
        self.setCentralWidget(central_widget)
        central_layout = QHBoxLayout(central_widget)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        # -- LEFT SLIM PASTEL DOCK (Navigation) --
        nav_rail = QFrame()
        nav_rail.setFixedWidth(72)
        nav_rail.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border-right: 1px solid rgba(139, 126, 200, 0.2);
            }
        """)
        nav_layout = QVBoxLayout(nav_rail)
        nav_layout.setContentsMargins(6, 16, 6, 16)
        nav_layout.setSpacing(20)

        # Logo Badge in Pastel Lilac
        logo_container = QWidget()
        logo_layout = QHBoxLayout(logo_container)
        logo_layout.setContentsMargins(0, 0, 0, 0)
        logo_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        logo = QLabel("OC")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedSize(38, 38)
        logo.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #8b7ec8, stop:1 #5e5298);
            color: #ffffff;
            font-weight: 800;
            font-size: 15px;
            border-radius: 10px;
            border: 1px solid rgba(139, 126, 200, 0.3);
        """)
        logo_layout.addWidget(logo)
        nav_layout.addWidget(logo_container)

        # Nav Buttons
        def create_nav_btn(text: str) -> QPushButton:
            btn = QPushButton(text)
            btn.setFixedHeight(48)
            btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #5c6479;
                    border: none;
                    border-radius: 8px;
                    font-size: 10px;
                    font-weight: bold;
                    letter-spacing: 0.6px;
                }
                QPushButton:hover {
                    background-color: #f4f2fb;
                    color: #5e5298;
                }
                QPushButton:checked {
                    background-color: #e8e4f7;
                    color: #5e5298;
                    border-left: 3px solid #5e5298;
                    border-radius: 6px;
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

        # User profile badge at bottom of dock
        user_badge = QLabel("VK")
        user_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        user_badge.setFixedSize(34, 34)
        user_badge.setStyleSheet("""
            background-color: #f4f2fb;
            color: #5e5298;
            font-weight: bold;
            font-size: 11px;
            border: 1px solid rgba(139, 126, 200, 0.35);
            border-radius: 10px;
        """)
        user_layout = QHBoxLayout()
        user_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        user_layout.addWidget(user_badge)
        nav_layout.addLayout(user_layout)

        # -- RIGHT MAIN AREA --
        right_area = QWidget()
        right_area.setStyleSheet("background-color: #f7f8fc;")
        right_layout = QVBoxLayout(right_area)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Top Bar (Pastel Chrome)
        top_bar = QFrame()
        top_bar.setFixedHeight(50)
        top_bar.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border-bottom: 1px solid rgba(139, 126, 200, 0.18);
            }
        """)
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(20, 0, 20, 0)
        top_bar_layout.setSpacing(12)

        # Brand / App Header
        brand_lbl = QLabel("OPENCLAW")
        brand_lbl.setStyleSheet("color: #141c29; font-size: 13px; font-weight: 800; letter-spacing: 0.5px; border: none;")
        top_bar_layout.addWidget(brand_lbl)

        ver_badge = QLabel("v2.4 PRO")
        ver_badge.setStyleSheet("""
            background-color: #e8e4f7;
            color: #5e5298;
            font-size: 10px;
            font-family: 'JetBrains Mono', Consolas, monospace;
            font-weight: 700;
            padding: 2px 7px;
            border-radius: 9px;
            border: 1px solid rgba(139, 126, 200, 0.3);
        """)
        top_bar_layout.addWidget(ver_badge)

        top_bar_layout.addSpacing(12)

        # Status Badges
        self._sys_status_pill = QLabel("● SYSTEM ACTIVE")
        self._sys_status_pill.setStyleSheet("""
            background-color: #e1f5ef;
            color: #186a59;
            font-size: 11px;
            font-weight: bold;
            padding: 3px 10px;
            border-radius: 11px;
            border: 1px solid #a3eed8;
        """)
        top_bar_layout.addWidget(self._sys_status_pill)

        self._ollama_status_pill = QLabel("Ollama: Loading...")
        self._ollama_status_pill.setStyleSheet("""
            background-color: #f4f2fb;
            color: #493c81;
            font-size: 11px;
            font-family: 'JetBrains Mono', Consolas, monospace;
            font-weight: bold;
            padding: 3px 10px;
            border-radius: 11px;
            border: 1px solid rgba(139, 126, 200, 0.3);
        """)
        top_bar_layout.addWidget(self._ollama_status_pill)

        self._info_lbl = QLabel("Initializing system checks...")
        self._info_lbl.setStyleSheet("color: #5c6479; font-size: 11px; border: none;")
        top_bar_layout.addWidget(self._info_lbl)

        top_bar_layout.addStretch()

        right_layout.addWidget(top_bar)

        # Stacked Workspaces
        self._setup = SetupWorkspace(runtime)
        self._process = ProcessWorkspace(runtime)
        self._history = JobPipelineWorkspace(runtime)

        self._stacked = QStackedWidget()
        self._stacked.setStyleSheet("background-color: #f7f8fc;")
        self._stacked.addWidget(self._setup)
        self._stacked.addWidget(self._process)
        self._stacked.addWidget(self._history)
        right_layout.addWidget(self._stacked)

        # Bottom Bar for Pastel System Telemetry
        bottom_bar = QFrame()
        bottom_bar.setFixedHeight(36)
        bottom_bar.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border-top: 1px solid rgba(139, 126, 200, 0.18);
            }
        """)
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(20, 0, 20, 0)
        bottom_layout.setSpacing(24)

        telemetry_lbl = QLabel("TELEMETRY:")
        telemetry_lbl.setStyleSheet("color: #8f96a8; font-size: 10px; font-weight: bold; font-family: 'JetBrains Mono', monospace; border: none;")
        bottom_layout.addWidget(telemetry_lbl)

        self._cpu_widget = MetricWidget("CPU", color="#93c5fd", track_color="#e0f2fe")
        self._ram_widget = MetricWidget("RAM", color="#fbbd9e", track_color="#fff0e8")
        self._gpu_widget = MetricWidget("GPU", color="#78c2ad", track_color="#e1f5ef")
        self._vram_widget = MetricWidget("VRAM", color="#f4a8b8", track_color="#ffdad6")

        bottom_layout.addWidget(self._cpu_widget, stretch=1)
        bottom_layout.addWidget(self._ram_widget, stretch=1)
        bottom_layout.addWidget(self._gpu_widget, stretch=1)
        bottom_layout.addWidget(self._vram_widget, stretch=1)

        right_layout.addWidget(bottom_bar)

        central_layout.addWidget(nav_rail)
        central_layout.addWidget(right_area)

        # Tab Navigation Connections
        self._btn_setup.clicked.connect(lambda: self._stacked.setCurrentIndex(0))
        self._btn_process.clicked.connect(lambda: self._stacked.setCurrentIndex(1))
        self._btn_history.clicked.connect(lambda: self._stacked.setCurrentIndex(2))

        # Start Monitor Thread
        self._monitor_thread = SystemMonitorThread(self)
        self._monitor_thread.setObjectName("SystemMonitorThread")
        self._monitor_thread.metrics_updated.connect(self._update_metrics)
        self._monitor_thread.start()

    def _update_metrics(self, cpu: float, ram: float, gpu: float, vram: float) -> None:
        def update_single_metric(widget: MetricWidget, new_val: float) -> None:
            old_val = widget.pb.value()
            int_val = int(new_val)
            widget.pb.setValue(int_val)
            widget.lbl.setText(f"{widget.label_prefix} {int_val}%")

            # Highlight jump > 5% (increasing or decreasing)
            if abs(int_val - old_val) > 5:
                widget.pb.setFixedHeight(10)
                widget.pb.setStyleSheet(f"""
                    QProgressBar {{
                        background-color: {widget.track_color}; border-radius: 5px;
                    }}
                    QProgressBar::chunk {{
                        background-color: #fbbd9e; border-radius: 5px;
                    }}
                """)

                # Restore original style
                def restore() -> None:
                    widget.pb.setFixedHeight(6)
                    widget.pb.setStyleSheet(f"""
                        QProgressBar {{
                            background-color: {widget.track_color}; border-radius: 3px; border: none;
                        }}
                        QProgressBar::chunk {{
                            background-color: {widget.color}; border-radius: 3px;
                        }}
                    """)

                from PySide6.QtCore import QTimer

                QTimer.singleShot(2000, restore)

        update_single_metric(self._cpu_widget, cpu)
        update_single_metric(self._ram_widget, ram)
        update_single_metric(self._gpu_widget, gpu)
        update_single_metric(self._vram_widget, vram)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._monitor_thread.requestInterruption()
        self._monitor_thread.wait(1500)
        if hasattr(self, "_health_thread") and self._health_thread.isRunning():
            self._health_thread.requestInterruption()
            self._health_thread.wait(1000)
        if hasattr(self, "_process"):
            self._process.cleanup()
        super().closeEvent(event)

    async def _on_task_changed(self, event: RuntimeEvent) -> None:
        self.event_received.emit(event)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        # Run health check on startup only once without blocking UI
        if not hasattr(self, "_health_checked"):
            self._health_checked = True
            self._run_system_health_check()

    def _run_system_health_check(self) -> None:
        from openclaw.plugins.ollama import OLLAMA_CLIENT_SERVICE, OllamaClient

        try:
            client = self._runtime.services.get(OLLAMA_CLIENT_SERVICE)
        except LookupError:
            self._sys_status_pill.setText("● SYSTEM ACTIVE")
            self._ollama_status_pill.setText("Ollama: Missing")
            self._ollama_status_pill.setStyleSheet("""
                background-color: #ffdad6; color: #ba1a1a;
                font-size: 11px; font-family: 'JetBrains Mono', Consolas, monospace; font-weight: bold;
                padding: 3px 10px; border-radius: 11px; border: 1px solid #ffb2bf;
            """)
            self._info_lbl.setText("Ollama plugin is not loaded.")
            self._info_lbl.setStyleSheet("color: #ba1a1a; font-size: 11px; border: none;")
            return

        import typing

        ollama = typing.cast(OllamaClient, client)

        class HealthCheckThread(QThread):
            finished_check = Signal(bool, bool, object)

            def __init__(
                self, ollama_client: OllamaClient, parent: QObject | None = None
            ) -> None:
                super().__init__(parent)
                self.setObjectName("HealthCheckThread")
                self.ollama = ollama_client

            def run(self) -> None:
                has_ollama = self.ollama.check_ollama_availability()
                server_up = False
                models: list[str] = []
                if has_ollama:
                    try:
                        server_up = self.ollama.check_connection()
                        if server_up:
                            models = self.ollama.get_available_models()
                    except Exception as e:
                        logger.debug("health check probe failed: %s", e)
                self.finished_check.emit(has_ollama, server_up, models)

        self._health_thread = HealthCheckThread(ollama, self)
        self._health_thread.finished_check.connect(self._on_health_check_done)
        self._health_thread.start()

    def _on_health_check_done(self, has_ollama: bool, server_up: bool, models: list[str]) -> None:
        model_name = models[0] if models else "None"
        
        if has_ollama and server_up and models:
            self._ollama_status_pill.setText(f"Ollama: {model_name}")
            self._ollama_status_pill.setStyleSheet("""
                background-color: #f4f2fb; color: #493c81;
                font-size: 11px; font-family: 'JetBrains Mono', Consolas, monospace; font-weight: bold;
                padding: 3px 10px; border-radius: 11px; border: 1px solid rgba(139, 126, 200, 0.3);
            """)
            self._info_lbl.setText(f"System ready. Active Model: {model_name}")
            self._info_lbl.setStyleSheet("color: #5c6479; font-size: 11px; border: none;")
        elif not has_ollama:
            self._ollama_status_pill.setText("Ollama: Not Found")
            self._ollama_status_pill.setStyleSheet("""
                background-color: #ffdad6; color: #ba1a1a;
                font-size: 11px; font-family: 'JetBrains Mono', Consolas, monospace; font-weight: bold;
                padding: 3px 10px; border-radius: 11px; border: 1px solid #ffb2bf;
            """)
            self._info_lbl.setText("Ollama is not installed or not in PATH.")
            self._info_lbl.setStyleSheet("color: #ba1a1a; font-size: 11px; border: none;")
        elif not server_up:
            self._ollama_status_pill.setText("Ollama: Offline")
            self._ollama_status_pill.setStyleSheet("""
                background-color: #fff0e8; color: #c25e36;
                font-size: 11px; font-family: 'JetBrains Mono', Consolas, monospace; font-weight: bold;
                padding: 3px 10px; border-radius: 11px; border: 1px solid #fbbd9e;
            """)
            self._info_lbl.setText("Ollama is installed but the server is not running.")
            self._info_lbl.setStyleSheet("color: #c25e36; font-size: 11px; border: none;")
        else:
            self._ollama_status_pill.setText("Ollama: No Models")
            self._ollama_status_pill.setStyleSheet("""
                background-color: #fff0e8; color: #c25e36;
                font-size: 11px; font-family: 'JetBrains Mono', Consolas, monospace; font-weight: bold;
                padding: 3px 10px; border-radius: 11px; border: 1px solid #fbbd9e;
            """)
            self._info_lbl.setText("Ollama server is running, but no models found.")
            self._info_lbl.setStyleSheet("color: #c25e36; font-size: 11px; border: none;")
