# OpenClaw — continuation handoff

## Goal and operating constraints

OpenClaw is a local, desktop-first AI automation runtime for human-in-the-loop job-search work.

- Local execution only; no cloud/API dependency.
- Manual user action must gate sensitive work.
- Every capability is a plugin; the core runtime must not depend on a specific capability.
- Keep strong typing, tests, Ruff, and MyPy clean.
- Do not automate resume submission or invent resume facts.

## Repository and status

- Repository: `C:\Users\Vijay\Documents\Codex\2026-08-04\ATS-Evader\openclaw`
- Git is initialized and the baseline codebase, including the Setup Workspace redesign, has been committed.
- Last verification passed: **pytest tests, Ruff, and MyPy**.
- Python environment: uv / CPython 3.14.6. Project requires Python >=3.12.

## Run commands

```powershell
cd C:\Users\Vijay\Documents\Codex\2026-08-04\ATS-Evader\openclaw
uv run pytest
uv run ruff check .
uv run mypy src
uv run openclaw
```

## Local AI state

- Ollama is running locally. Connection logic automatically boots Ollama if it is off.
- Installed models confirmed: `gemma4:12b` (default).
- The OpenClaw UI has successfully connected to local Ollama and parsed complex master resumes. 
- Network timeout increased to 600s to support heavy local inference.

## Current architecture

### Core runtime (`src/openclaw/core`)

- `config.py`: `RuntimeSettings`; local data directory and SQLite path.
- `events.py`: async in-process `EventBus` and `RuntimeEvent`.
- `tasks.py`: persisted task lifecycle; terminal tasks cannot transition again.
- `storage.py`: SQLModel/SQLite task repository. Upgraded with `StructuredResumeRecord` (tracks `is_active` and `created_at` timestamp) and `PreferenceRecord`.
- `services.py`: explicit runtime-owned `ServiceRegistry` for sharing plugin services.
- `runtime.py`: composition root; initializes DB, restores tasks, discovers and starts plugins.

### Plugin framework (`src/openclaw/plugins`)

- `manager.py`: plugin context, entry-point discovery.
- `ollama.py`: local Ollama HTTP client and service `ollama.client`. Includes auto-boot and connection checks.
- `ats.py`: depends on Ollama. 
  - `parse_master_resume(raw_text)`: Extracts structural JSON and Candidate/Role preferences.
  - `analyze(resume, job_description)` & `tailor(resume, job_description)`.

### Desktop UI (`src/openclaw/ui`)

- `main_window.py`: Orchestrates a `QStackedWidget` for the workspaces (Setup, Process, History) and a system metrics bottom bar that animates heavily.
- `setup_workspace.py`: Redesigned to accept a master resume, parse it via AI, track historical profiles (with a delete button), and toggle an active profile.
- `process_workspace.py`: Dynamically loads the "Target Profile" preferences out of the currently active master resume. Prepares a feed for incoming jobs.
- `terminal_loader.py`: A custom sequential task loader overlay with dynamic loading animations (simulating AI thought).

## Current UX

1. Start OpenClaw with `uv run openclaw`.
2. Open **Setup** tab to paste a master resume.
3. Watch the sequential loader check Ollama, parse the resume with `gemma4:12b`, and extract preferences (Name, Role, Location, etc.).
4. View the historical accordion of parsed resumes; set one as active or delete it.
5. Switch to the **Process** tab, where the Target Profile sidebar instantly refreshes to display the active resume's embedded preferences.

## Recent Changelog

### 1. Data Model & Storage Enhancements
- **Active Profile Tracking:** Modified `StructuredResume` and `StructuredResumeRecord` to include `created_at` and `is_active` flags, maintaining a full database of historical master resumes.
- **Repository Methods:** Added backend functions to toggle the active resume, fetch history, and permanently delete older resumes from the SQLite database.

### 2. UI & UX Redesign (Setup & Process)
- **Navigation Fix:** Fixed a core bug in `main_window.py` where workspace tabs weren't switching correctly.
- **The Setup Workspace:** Rebuilt `setup_workspace.py` to include a scrollable history container, an Active Profile card, and expandable accordions for Recent History with "Set as Active" and "Delete" actions.
- **The Process Workspace:** Wired `process_workspace.py` to dynamically refresh its sidebar based on the active profile from the Setup tab.
- **Animated Metrics Dock:** Built a reactive hardware monitor (CPU/RAM/GPU) that physically expands and changes color on utilization spikes.
- **Dynamic Loading Overlay:** Added a dynamic task loader in `terminal_loader.py` that generates random progress jumps to simulate AI thought and prevent UI freezing.

### 3. AI Pipeline & Parsing Robustness
- **Candidate Name Extraction:** Updated the `ats.py` prompt to explicitly extract `Candidate Name`.
- **Preferences Encapsulation:** Preferences are now permanently serialized directly into the specific resume payload that generated them, instead of a global dump table.
- **Inference Stability:** Increased local Ollama network timeout to 600 seconds for heavy models (e.g., `gemma4:12b`).
- **JSON Validation:** Added regex/string cleaning to strip accidental markdown block formatting hallucinated by local LLMs.

## Recommended next steps (in order)

1. **Cover Letter Generator.** Use the local LLM to generate targeted cover letters based on the job description and the user's base profile, integrated into the ATS plugin.
2. **Eligibility Engine.** Add a rules-based filter to automatically reject jobs that don't meet basic criteria (salary, location, remote status, min experience) before sending them to the heavier ATS LLM analysis.
3. **Full Auto-Apply Pipeline (Browser Automation).** Click "Start Job Hunt" in the Process tab to launch the background browser, navigate to a job board, scrape job descriptions, run them through the Eligibility Engine and ATS match, and bubble them up in the Process feed for "Approve & Apply".
4. **Document ingestion.** Add a separate local plugin for importing `.docx` and PDF text, avoiding copy-paste.
