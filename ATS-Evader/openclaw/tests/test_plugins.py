from pathlib import Path

from openclaw.core.config import RuntimeSettings
from openclaw.core.events import EventBus
from openclaw.core.services import ServiceRegistry
from openclaw.core.storage import SQLiteDocumentRepository, SQLiteTaskRepository
from openclaw.core.tasks import TaskManager
from openclaw.plugins.manager import PluginContext, PluginManager


class ExamplePlugin:
    name = "example"
    requires: tuple[str, ...] = ()

    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    async def start(self, context: PluginContext) -> None:
        self.calls.append("start")

    async def stop(self) -> None:
        self.calls.append("stop")


async def test_plugins_have_a_managed_lifecycle(tmp_path: Path) -> None:
    calls: list[str] = []
    repository = SQLiteTaskRepository(tmp_path / "tasks.sqlite")
    repository.initialize()
    events = EventBus()
    documents = SQLiteDocumentRepository(tmp_path / "documents.sqlite")
    context = PluginContext(RuntimeSettings(), events, TaskManager(events, repository), documents, ServiceRegistry())
    manager = PluginManager(context)
    manager.register("example", lambda: ExamplePlugin(calls))

    await manager.start_all()
    await manager.stop_all()

    assert calls == ["start", "stop"]


async def test_plugin_lifecycle_events_are_published(tmp_path: Path) -> None:
    events = EventBus()
    repository = SQLiteTaskRepository(tmp_path / "tasks.sqlite")
    repository.initialize()
    documents = SQLiteDocumentRepository(tmp_path / "documents.sqlite")
    manager = PluginManager(
        PluginContext(RuntimeSettings(), events, TaskManager(events, repository), documents, ServiceRegistry())
    )
    received: list[str] = []

    async def record(event: object) -> None:
        received.append(str(event))

    events.subscribe("plugin.started", record)
    events.subscribe("plugin.stopped", record)
    manager.register("example", lambda: ExamplePlugin([]))

    await manager.start_all()
    await manager.stop_all()

    assert len(received) == 2
