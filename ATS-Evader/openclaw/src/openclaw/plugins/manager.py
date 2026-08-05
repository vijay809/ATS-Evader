"""Plugin contracts, discovery, and lifecycle management."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import Protocol, cast

from openclaw.core.config import RuntimeSettings
from openclaw.core.events import EventBus, RuntimeEvent
from openclaw.core.services import ServiceRegistry
from openclaw.core.storage import DocumentRepository
from openclaw.core.tasks import TaskManager

PLUGIN_ENTRY_POINT_GROUP = "openclaw.plugins"


@dataclass(frozen=True, slots=True)
class PluginContext:
    """Runtime services deliberately exposed to capability plugins."""

    settings: RuntimeSettings
    events: EventBus
    tasks: TaskManager
    documents: DocumentRepository
    services: ServiceRegistry


class Plugin(Protocol):
    """A local capability whose lifecycle is controlled by the runtime."""

    name: str
    requires: tuple[str, ...]

    async def start(self, context: PluginContext) -> None: ...

    async def stop(self) -> None: ...


PluginFactory = Callable[[], Plugin]


class PluginManager:
    def __init__(self, context: PluginContext) -> None:
        self._context = context
        self._factories: dict[str, PluginFactory] = {}
        self._loaded: dict[str, Plugin] = {}

    @property
    def loaded_names(self) -> tuple[str, ...]:
        return tuple(self._loaded)

    def register(self, name: str, factory: PluginFactory) -> None:
        if name in self._factories:
            raise ValueError(f"Plugin already registered: {name}")
        self._factories[name] = factory

    def discover(self) -> tuple[str, ...]:
        """Register plugins packaged as ``openclaw.plugins`` entry points."""
        discovered: list[str] = []
        for plugin_entry_point in entry_points(group=PLUGIN_ENTRY_POINT_GROUP):
            factory = cast(PluginFactory, plugin_entry_point.load())
            self.register(plugin_entry_point.name, factory)
            discovered.append(plugin_entry_point.name)
        return tuple(discovered)

    async def start_all(self) -> None:
        starting: set[str] = set()
        try:
            for name in self._factories:
                await self._start(name, starting)
        except Exception:
            await self.stop_all()
            raise

    async def _start(self, name: str, starting: set[str]) -> None:
        if name in self._loaded:
            return
        if name in starting:
            raise ValueError(f"Circular plugin dependency: {name}")
        try:
            factory = self._factories[name]
        except KeyError as error:
            raise ValueError(f"Required plugin is not registered: {name}") from error

        starting.add(name)
        plugin = factory()
        for dependency in plugin.requires:
            await self._start(dependency, starting)
        await plugin.start(self._context)
        self._loaded[name] = plugin
        await self._context.events.publish(RuntimeEvent("plugin.started", {"name": name}))
        starting.remove(name)

    async def stop_all(self) -> None:
        for name, plugin in reversed(tuple(self._loaded.items())):
            await plugin.stop()
            await self._context.events.publish(RuntimeEvent("plugin.stopped", {"name": name}))
        self._loaded.clear()
