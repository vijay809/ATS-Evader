"""Service for executing natural language commands on a webpage using LLM."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from openclaw.plugins.ollama import OllamaClient
from openclaw.plugins.dom_extractor import DOMExtractor

if TYPE_CHECKING:
    from openclaw.plugins.browser import BrowserService

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an Agentic Web Browser. You are controlling a real web browser to help the user complete tasks.

You will be given the Current Page State (a list of interactive elements with IDs) and a User Command.

Your goal is to choose the single best action to execute the User Command.

# Available Actions
You MUST respond with EXACTLY ONE action formatted like this:
CLICK <id>
TYPE <id> "<text>"
DONE

Example 1:
Reasoning: I need to click the search button to submit the form.
Action: CLICK 15

Example 2:
Reasoning: The user wants to search for 'Python'. I will type it into the search box.
Action: TYPE 12 "Python"

Example 3:
Reasoning: The task is complete.
Action: DONE

Always include "Reasoning:" first, followed by "Action:".
"""

@dataclass
class SemanticResult:
    reasoning: str
    action: str
    success: bool
    error: str | None = None


class SemanticNavigator:
    def __init__(self, ollama_client: OllamaClient, browser_service: BrowserService) -> None:
        self._ollama = ollama_client
        self._browser = browser_service

    async def execute_command(self, command: str) -> SemanticResult:
        """Executes a single natural language command on the current browser page."""
        page = self._browser.page
        if not page or page.is_closed():
            return SemanticResult(reasoning="", action="", success=False, error="Browser page is not open.")

        # 1. Extract DOM
        try:
            future = asyncio.run_coroutine_threadsafe(DOMExtractor.get_interactive_state(page), self._browser._loop)
            dom_state = await asyncio.wrap_future(future)
        except Exception as e:
            return SemanticResult(reasoning="", action="", success=False, error=f"DOM Extraction failed: {e}")

        prompt = f"{SYSTEM_PROMPT}\n\nUser Command: {command}\n\n{dom_state}"
        
        # 2. Query LLM
        try:
            response = await self._ollama.generate(prompt)
            text = response.text
        except Exception as e:
            return SemanticResult(reasoning="", action="", success=False, error=f"LLM Generation failed: {e}")
            
        # 3. Parse LLM response
        reasoning = ""
        action = ""
        
        reasoning_match = re.search(r"Reasoning:\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
        action_match = re.search(r"Action:\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
        
        if reasoning_match:
            reasoning = reasoning_match.group(1).strip()
        if action_match:
            action = action_match.group(1).strip()
        else:
            return SemanticResult(reasoning=text, action="", success=False, error="Could not parse Action from LLM response.")

        # 4. Execute Action in Browser Thread
        try:
            future_exec = asyncio.run_coroutine_threadsafe(self._execute_playwright_action(action), self._browser._loop)
            await asyncio.wrap_future(future_exec)
        except Exception as e:
            return SemanticResult(reasoning=reasoning, action=action, success=False, error=f"Execution failed: {e}")
            
        return SemanticResult(reasoning=reasoning, action=action, success=True)

    async def _execute_playwright_action(self, action: str) -> None:
        """Runs inside the Browser thread."""
        page = self._browser.page
        if not page:
            raise RuntimeError("Page is missing")

        if action.upper().startswith("CLICK"):
            parts = action.split(" ")
            if len(parts) < 2:
                raise ValueError("CLICK requires an ID")
            agent_id = parts[1].strip()
            await page.locator(f'[data-agent-id="{agent_id}"]').click(timeout=3000)
            
        elif action.upper().startswith("TYPE"):
            # Extract ID and text
            match = re.match(r"TYPE\s+(\d+)\s+[\"'](.*)[\"']", action, re.IGNORECASE)
            if not match:
                raise ValueError("TYPE requires an ID and text in quotes")
            agent_id = match.group(1).strip()
            text = match.group(2)
            await page.locator(f'[data-agent-id="{agent_id}"]').fill(text, timeout=3000)
            
        elif action.upper().strip() == "DONE":
            pass
        else:
            raise ValueError(f"Unknown action format: {action}")
