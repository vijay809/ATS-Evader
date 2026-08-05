# OpenClaw — continuation handoff

## Goal and operating constraints

OpenClaw is a local, desktop-first AI automation runtime for human-in-the-loop job-search work.

- Local execution only; no cloud/API dependency.
- Manual user action must gate sensitive work.
- Every capability is a plugin; the core runtime must not depend on a specific capability.
- Keep strong typing, tests, Ruff, and MyPy clean.
- Do not automate resume submission or invent resume facts.

## Repository and status

- Repository: `C:\Users\Vijay\Documents\Codex\2026-08-04\referenced-chatgpt-conversation-this-is-an\openclaw`
- Git is initialized but **has no commit yet**. All current project files are untracked.
- Last verification passed: **14 pytest tests, Ruff, and MyPy**.
- Python environment: uv / CPython 3.14.6. Project requires Python >=3.12.

## Run commands

```powershell
cd C:\Users\Vijay\Documents\Codex\2026-08-04\referenced-chatgpt-conversation-this-is-an\openclaw
uv run pytest
uv run ruff check .
uv run mypy src
uv run openclaw
```

The Codex sandbox may fail to access Python. If that happens, rerun only these commands with the available approved/escalated local-runtime permission.

## Local AI state

- Ollama is running at `http://localhost:11434`.
- Installed models confirmed: `gemma4:12b` (default in OpenClaw) and `gpt-oss:latest`.
- The OpenClaw UI has successfully connected to local Ollama.

## Current architecture

### Core runtime (`src/openclaw/core`)

- `config.py`: `RuntimeSettings`; local data directory and SQLite path.
- `events.py`: async in-process `EventBus` and `RuntimeEvent`.
- `tasks.py`: persisted task lifecycle; terminal tasks cannot transition again.
- `storage.py`: SQLModel/SQLite task repository.
- `services.py`: explicit runtime-owned `ServiceRegistry` for sharing plugin services.
- `runtime.py`: composition root; initializes DB, restores tasks, discovers and starts plugins.

### Plugin framework (`src/openclaw/plugins`)

- `manager.py`: plugin context, entry-point discovery, dependency-aware startup, lifecycle events and cleanup.
- Plugins register under the Python entry-point group `openclaw.plugins` in `pyproject.toml`.
- `ollama.py`: local Ollama HTTP client and service `ollama.client`; default model `gemma4:12b`.
- `ats.py`: depends on Ollama and provides `ats.analyzer`.
  - `analyze(resume, job_description)`: structured score, keyword gaps, recommendations, and summary.
  - `tailor(resume, job_description)`: structured tailored-resume draft, change list, and warnings.
  - Tailoring prompt explicitly prohibits fabricating experience, skills, credentials, or metrics.

### Desktop UI (`src/openclaw/ui`)

- `main_window.py`: task table, activity console, task controls, Local AI dock, and ATS dock.
- `ai_workspace.py`: explicit local Ollama prompt/response interface; uses a background Qt thread and task tracking.
- `ats_workspace.py`: paste resume + job description; Analyze locally or Tailor resume locally; uses background workers and records tasks.
- `monitor.py`: Qt-independent task-row presentation mapping.

## Current UX

1. Start OpenClaw with `uv run openclaw`.
2. Use **Local AI** for a direct prompt to the selected local model.
3. Use **ATS analysis** to paste text, then choose:
   - **Analyze locally** for an ATS score/gap review.
   - **Tailor resume locally** for a grounded draft and warnings.
4. Review all generated content manually. No application submission exists or should be added without explicit confirmation controls.

## Important implementation notes

- Desktop callbacks use `asyncio.run(...)` for short task state updates; Ollama inference runs in a `QThread`, so the UI stays responsive.
- Plugins must define `name`, `requires`, `start(context)`, and `stop()`.
- Plugin dependency startup is recursive in `PluginManager._start`.
- UI docks are currently read/paste-oriented; no resume or job documents are persisted beyond task records.
- The ATS JSON parser handles plain JSON and fenced JSON only. Models can still produce malformed output; improve robustness before treating output as production-grade.

## Recommended next steps (in order)

1. **Commit the baseline.** Review `git status`, then make the first commit before larger changes.
2. **Manual acceptance test.** Launch the UI; use a small anonymized resume/job description to test Analyze and Tailor with `gemma4:12b`. Record any malformed JSON or UI behavior.
3. **Harden structured model output.** Add JSON extraction/repair retries, schema-validation feedback, and tests for common fenced/prose responses. Keep failures visible to the user.
4. **Persist user work.** Add SQLModel entities/repositories for resumes, job descriptions, analyses, and tailored drafts. Design migrations deliberately; do not store raw data outside the configured local DB.
5. **Document ingestion.** Add a separate local plugin for importing `.docx` and PDF text, with preview/confirmation before storing. Do not silently overwrite original files.
6. **Review workflow.** Add side-by-side original/draft comparison, editable draft text, an explicit approval state, and export only after user action.
7. **Only then consider browser/job-search capability.** Make it a separate plugin with visible session state, per-action confirmation, audit events, and no auto-submit behavior.

## Useful test locations

- `tests/test_tasks.py`: task events and persistence.
- `tests/test_runtime.py`: DB startup/task restoration/local Ollama service registration.
- `tests/test_plugins.py`: lifecycle and events.
- `tests/test_ollama.py`: local-client payload/error behavior without a server.
- `tests/test_ats.py`: structured ATS analysis and tailoring parsing.
- `tests/test_monitor.py`, `tests/test_task_controls.py`: UI-independent presentation/lifecycle behavior.
