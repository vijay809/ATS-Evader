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

## Step-by-Step Guide for Users

Welcome to OpenClaw! This tool acts as your local, human-in-the-loop AI assistant for job applications. Here is how to get started:

### 1. Prerequisites
Ensure you have the following installed on your machine:
- **Python 3.12** or higher.
- **[uv](https://docs.astral.sh/uv/)** (the fast Python package installer and resolver).
- **[Ollama](https://ollama.com/)** running locally.

### 2. Set Up Local AI (Ollama)
OpenClaw uses local AI to keep your data private.
1. Open your terminal and pull the recommended model:
   ```powershell
   ollama pull gemma4:12b
   ```
2. Make sure Ollama is running in the background (usually `ollama serve`).

### 3. Launch OpenClaw
1. Open a terminal and navigate to your OpenClaw folder:
   ```powershell
   cd C:\path\to\openclaw
   ```
2. Sync the dependencies and start the application:
   ```powershell
   uv sync
   uv run openclaw
   ```
3. The OpenClaw desktop interface will appear.

### 4. How to Use ATS Analysis
1. In the main window, open the **ATS Workspace**.
2. **Paste** your Resume and the Job Description into the respective text boxes.
3. Click **Analyze locally**. The AI will generate an ATS score, identify missing keywords, and suggest improvements. This happens completely on your machine.
4. If you want a customized draft, click **Tailor resume locally**. OpenClaw will restructure your resume to better fit the job.
5. **Review everything.** The tool explicitly warns against fabricating information, but you are responsible for ensuring the final resume is accurate before you apply.

### 5. Viewing Activity and Logs
- The **Console** at the bottom of the screen displays real-time logs of what the system is doing.
- The **Tasks** table tracks the progress of ongoing operations (like when the AI is currently thinking or when you start a new analysis).
