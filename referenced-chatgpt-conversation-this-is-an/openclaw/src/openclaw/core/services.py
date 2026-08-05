"""Runtime-owned registry for explicitly shared plugin services."""

from __future__ import annotations

from typing import Any


class ServiceRegistry:
    """A small, explicit dependency boundary between independently packaged plugins."""

    def __init__(self) -> None:
        self._services: dict[str, Any] = {}

    def provide(self, name: str, service: object) -> None:
        if name in self._services:
            raise ValueError(f"Service already provided: {name}")
        self._services[name] = service

    def remove(self, name: str) -> None:
        self._services.pop(name, None)

    def get(self, name: str) -> object:
        try:
            return self._services[name]
        except KeyError as error:
            raise LookupError(f"Service is unavailable: {name}") from error

    def names(self) -> tuple[str, ...]:
        return tuple(self._services)
