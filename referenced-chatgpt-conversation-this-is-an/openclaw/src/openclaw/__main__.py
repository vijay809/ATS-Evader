"""Desktop application entry point."""

import asyncio
import sys

from PySide6.QtWidgets import QApplication

from openclaw.core.config import RuntimeSettings
from openclaw.core.runtime import Runtime
from openclaw.ui.main_window import MainWindow


def main() -> int:
    runtime = Runtime(RuntimeSettings())
    asyncio.run(runtime.start())
    app = QApplication(sys.argv)
    window = MainWindow(runtime)
    window.show()
    try:
        return app.exec()
    finally:
        asyncio.run(runtime.stop())


if __name__ == "__main__":
    raise SystemExit(main())
