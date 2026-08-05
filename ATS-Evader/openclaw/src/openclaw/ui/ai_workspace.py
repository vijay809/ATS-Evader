"""Human-controlled desktop workspace for local Ollama generation."""

from __future__ import annotations

import asyncio
from uuid import UUID

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from openclaw.core.runtime import Runtime
from openclaw.core.tasks import TaskStatus
from openclaw.plugins.ollama import (
    OLLAMA_CLIENT_SERVICE,
    OllamaClient,
    OllamaCompletion,
    OllamaUnavailableError,
)


class GenerationWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, client: OllamaClient, prompt: str, model: str) -> None:
        super().__init__()
        self._client = client
        self._prompt = prompt
        self._model = model

    def run(self) -> None:
        try:
            completion = asyncio.run(self._client.generate(self._prompt, model=self._model))
        except (OllamaUnavailableError, ValueError) as error:
            self.failed.emit(str(error))
            return
        self.completed.emit(completion)


class AiWorkspace(QWidget):
    """Explicit, human-initiated prompts sent only to the local Ollama server."""

    def __init__(self, runtime: Runtime) -> None:
        super().__init__()
        self._runtime = runtime
        self._current_task_id: UUID | None = None
        self._worker: GenerationWorker | None = None

        self._model = QLineEdit("gemma4:12b")
        self._prompt = QPlainTextEdit()
        self._prompt.setPlaceholderText("Ask the local model to analyze, draft, or summarize...")
        self._response = QPlainTextEdit()
        self._response.setReadOnly(True)
        self._status = QLabel("Ready. Requests are sent only when you click Generate.")
        self._generate_button = QPushButton("Generate locally")
        self._generate_button.clicked.connect(self.generate)

        form = QFormLayout()
        form.addRow("Model", self._model)
        form.addRow("Prompt", self._prompt)
        controls = QHBoxLayout()
        controls.addWidget(self._generate_button)
        controls.addWidget(self._status)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(controls)
        layout.addWidget(QLabel("Response"))
        layout.addWidget(self._response)

    def generate(self) -> None:
        prompt = self._prompt.toPlainText().strip()
        model = self._model.text().strip()
        if not prompt or not model:
            self._set_status("Enter both a model and prompt.")
            return
        try:
            client = self._runtime.services.get(OLLAMA_CLIENT_SERVICE)
        except LookupError:
            self._set_status("The Ollama plugin is unavailable.")
            return
        if not isinstance(client, OllamaClient):
            self._set_status("The registered Ollama service is invalid.")
            return

        task = asyncio.run(self._runtime.tasks.create(f"Local AI: {prompt[:60]}"))
        asyncio.run(self._runtime.tasks.transition(task.id, TaskStatus.RUNNING, model))
        self._current_task_id = task.id
        self._response.clear()
        self._generate_button.setEnabled(False)
        self._set_status("Generating with local Ollama...")
        self._worker = GenerationWorker(client, prompt, model)
        self._worker.completed.connect(self._show_completion)
        self._worker.failed.connect(self._show_failure)
        self._worker.start()

    def _show_completion(self, completion: object) -> None:
        if not isinstance(completion, OllamaCompletion):
            self._show_failure("The Ollama plugin returned an invalid completion.")
            return
        self._response.setPlainText(completion.text)
        self._finish_task(TaskStatus.SUCCEEDED, f"Completed with {completion.model}")
        self._set_status(f"Completed with {completion.model}.")

    def _show_failure(self, message: str) -> None:
        self._finish_task(TaskStatus.FAILED, message)
        self._set_status(f"Generation failed: {message}")

    def _finish_task(self, status: TaskStatus, detail: str) -> None:
        if self._current_task_id is not None:
            asyncio.run(self._runtime.tasks.transition(self._current_task_id, status, detail))
            self._current_task_id = None
        self._generate_button.setEnabled(True)
        self._worker = None

    def _set_status(self, message: str) -> None:
        self._status.setText(message)
