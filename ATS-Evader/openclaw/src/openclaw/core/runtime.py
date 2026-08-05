"""Composition root for runtime infrastructure."""

from openclaw.core.config import RuntimeSettings
from openclaw.core.events import EventBus
from openclaw.core.services import ServiceRegistry
from openclaw.core.storage import SQLiteTaskRepository
from openclaw.core.tasks import TaskManager
from openclaw.plugins.manager import PluginContext, PluginManager


class Runtime:
    def __init__(self, settings: RuntimeSettings) -> None:
        self.settings = settings
        self.events = EventBus()
        self.services = ServiceRegistry()
        self.task_repository = SQLiteTaskRepository(settings.database_path)
        self.tasks = TaskManager(self.events, self.task_repository)
        self.plugins = PluginManager(PluginContext(settings, self.events, self.tasks, self.services))

    async def start(self) -> None:
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.task_repository.initialize()
        self.tasks.restore(tuple(self.task_repository.list()))
        self.plugins.discover()
        await self.plugins.start_all()

    async def stop(self) -> None:
        await self.plugins.stop_all()
