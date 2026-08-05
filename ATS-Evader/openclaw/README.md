# OpenClaw

OpenClaw is a local, desktop-first automation runtime. The core runtime owns orchestration,
observability, configuration, and persistence boundaries; capabilities are supplied by plugins.

## Development

Install Python 3.12 and [uv](https://docs.astral.sh/uv/), then run:

```powershell
uv sync --extra dev
uv run pytest
uv run openclaw
```

The initial implementation intentionally has no bundled capability plugins. It demonstrates the
runtime contracts and a minimal desktop shell without coupling the runtime to PySide6.

## Plugins

Capability packages can register a zero-argument plugin factory through the `openclaw.plugins`
Python entry-point group. The runtime discovers those packages at startup and passes each plugin a
`PluginContext` containing only settings, events, and task services.

### Ollama

The bundled Ollama plugin registers a local `ollama.client` service. Start Ollama locally and pull
the configured model before adding a feature that calls it:

```powershell
ollama pull gemma4:12b
ollama serve
```

### ATS analysis

The ATS plugin sends pasted resume and job-description text to your selected local model and asks
for a structured comparison. It never edits a resume or submits an application automatically; you
review recommendations in the desktop workspace before taking any action.

The same workspace can produce a tailored resume draft. Its prompt explicitly prevents inventing
experience or qualifications; you still review all wording and warnings before using the draft.
