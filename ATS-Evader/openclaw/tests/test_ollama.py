import pytest

from openclaw.plugins.ollama import OllamaClient, OllamaSettings, OllamaUnavailableError


async def test_generate_uses_the_configured_local_endpoint() -> None:
    sent: dict[str, object] = {}

    def sender(url: str, payload: dict[str, object], timeout: float) -> dict[str, object]:
        sent.update(url=url, payload=payload, timeout=timeout)
        return {"model": "test-model", "response": "Tailored summary"}

    client = OllamaClient(OllamaSettings(base_url="http://localhost:11434"), sender)

    completion = await client.generate("Summarize this job", model="test-model")

    assert completion.text == "Tailored summary"
    assert sent["url"] == "http://localhost:11434/api/generate"
    assert sent["payload"] == {"model": "test-model", "prompt": "Summarize this job", "stream": False}


async def test_generate_rejects_empty_prompts() -> None:
    client = OllamaClient(OllamaSettings(), lambda _url, _payload, _timeout: {})

    with pytest.raises(ValueError, match="must not be empty"):
        await client.generate("  ")


async def test_generate_rejects_invalid_server_responses() -> None:
    client = OllamaClient(OllamaSettings(), lambda _url, _payload, _timeout: {})

    with pytest.raises(OllamaUnavailableError, match="without generated text"):
        await client.generate("Create a summary")
