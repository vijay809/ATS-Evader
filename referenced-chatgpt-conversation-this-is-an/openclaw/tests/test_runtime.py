from pathlib import Path

from openclaw.core.config import RuntimeSettings
from openclaw.core.runtime import Runtime
from openclaw.core.tasks import TaskStatus
from openclaw.plugins.ollama import OLLAMA_CLIENT_SERVICE, OllamaClient


async def test_start_creates_the_runtime_database(tmp_path: Path) -> None:
    settings = RuntimeSettings(data_dir=tmp_path)
    runtime = Runtime(settings)

    await runtime.start()
    await runtime.stop()

    assert settings.database_path.exists()


async def test_runtime_registers_the_local_ollama_client(tmp_path: Path) -> None:
    runtime = Runtime(RuntimeSettings(data_dir=tmp_path))

    await runtime.start()

    assert isinstance(runtime.services.get(OLLAMA_CLIENT_SERVICE), OllamaClient)
    await runtime.stop()


async def test_start_restores_existing_tasks(tmp_path: Path) -> None:
    settings = RuntimeSettings(data_dir=tmp_path)
    first_runtime = Runtime(settings)
    await first_runtime.start()
    task = await first_runtime.tasks.create("Tailor resume")
    await first_runtime.tasks.transition(task.id, TaskStatus.RUNNING)
    await first_runtime.stop()

    restored_runtime = Runtime(settings)
    await restored_runtime.start()

    assert restored_runtime.tasks.get(task.id).status is TaskStatus.RUNNING
    await restored_runtime.stop()
