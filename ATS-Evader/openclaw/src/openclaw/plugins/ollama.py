"""Local Ollama capability plugin and its typed HTTP client."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field

from openclaw.plugins.manager import PluginContext

OLLAMA_CLIENT_SERVICE = "ollama.client"


class OllamaSettings(BaseModel):
    base_url: str = "http://127.0.0.1:11434"
    default_model: str = "gemma4:12b"
    timeout_seconds: float = Field(default=600.0, gt=0)


@dataclass(frozen=True, slots=True)
class OllamaCompletion:
    model: str
    text: str


class OllamaUnavailableError(RuntimeError):
    """The local Ollama server could not be reached or returned invalid data."""


JsonSender = Callable[[str, dict[str, Any], float], dict[str, Any]]


class OllamaClient:
    def __init__(self, settings: OllamaSettings, sender: JsonSender | None = None) -> None:
        self._settings = settings
        self._sender = sender or self._send_json

    async def generate(self, prompt: str, *, model: str | None = None) -> OllamaCompletion:
        if not prompt.strip():
            raise ValueError("Prompt must not be empty")
        selected_model = model or self._settings.default_model
        response = await asyncio.to_thread(
            self._sender,
            f"{self._settings.base_url.rstrip('/')}/api/generate",
            {"model": selected_model, "prompt": prompt, "stream": False},
            self._settings.timeout_seconds,
        )
        text = response.get("response")
        if not isinstance(text, str):
            raise OllamaUnavailableError("Ollama returned a response without generated text")
        returned_model = response.get("model", selected_model)
        return OllamaCompletion(model=str(returned_model), text=text)
    def check_ollama_availability(self) -> bool:
        """Check if the ollama executable is available in PATH."""
        import shutil
        return shutil.which("ollama") is not None

    def boot_ollama(self) -> None:
        """Start the local Ollama daemon in the background."""
        import subprocess
        # Use CREATE_NO_WINDOW on Windows to prevent a command prompt from flashing
        creationflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags
        )

    def get_available_models(self) -> list[str]:
        """Fetch the list of installed model names from the local Ollama server."""
        from urllib.request import urlopen, Request
        import json
        try:
            req = Request(f"{self._settings.base_url.rstrip('/')}/api/tags", headers={"User-Agent": "OpenClaw/1.0"})
            with urlopen(req, timeout=2.0) as response:
                result = json.load(response)
                return [m.get("name") for m in result.get("models", []) if "name" in m]
        except Exception:
            return []

    def check_connection(self) -> bool:
        """Verify the Ollama server is running by fetching tags."""
        from urllib.request import urlopen, Request
        import json
        try:
            req = Request(f"{self._settings.base_url.rstrip('/')}/api/tags", headers={"User-Agent": "OpenClaw/1.0"})
            with urlopen(req, timeout=2.0) as response:
                result = json.load(response)
                return "models" in result
        except Exception as e:
            raise Exception(f"Connection failed: {e}")

    @staticmethod
    def _send_json(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                result = json.load(response)
        except (URLError, OSError, json.JSONDecodeError) as error:
            error_details = str(error)
            if hasattr(error, "read"):
                # It's likely an HTTPError with a body
                try:
                    error_details += " - " + error.read().decode("utf-8")
                except Exception:
                    pass
            raise OllamaUnavailableError(f"Unable to reach the local Ollama server: {error_details}") from error
        if not isinstance(result, dict):
            raise OllamaUnavailableError("Ollama returned an unexpected response")
        return result


class OllamaPlugin:
    name = "ollama"
    requires: tuple[str, ...] = ()

    def __init__(self, settings: OllamaSettings | None = None) -> None:
        self._settings = settings or OllamaSettings()
        self._context: PluginContext | None = None

    async def start(self, context: PluginContext) -> None:
        context.services.provide(OLLAMA_CLIENT_SERVICE, OllamaClient(self._settings))
        self._context = context

    async def stop(self) -> None:
        if self._context is not None:
            self._context.services.remove(OLLAMA_CLIENT_SERVICE)
            self._context = None


def create_plugin() -> OllamaPlugin:
    return OllamaPlugin()
