"""Playwright browser plugin with stealth and LLM-assisted navigation."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
from playwright_stealth import stealth  # type: ignore[import-untyped]

from openclaw.core.events import RuntimeEvent
from openclaw.plugins.manager import PluginContext

logger = logging.getLogger(__name__)

BROWSER_SERVICE = "browser.agent"


class BrowserService:
    def __init__(self, context: PluginContext) -> None:
        self._context = context
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._browser_context: BrowserContext | None = None
        self._page: Page | None = None

    def _on_disconnected(self, browser: Browser) -> None:
        self._page = None
        self._browser_context = None
        self._browser = None
        if self._context:
            # Optionally publish event (cannot await directly here as it's sync callback)
            pass

    async def launch(self, url: str | None = None) -> None:
        if self._browser is not None:
            if url and self._page:
                await self._page.goto(url)
            return

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=False)
        self._browser.on("disconnected", self._on_disconnected)
        self._browser_context = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        )
        self._page = await self._browser_context.new_page()
        await stealth(self._page)
        
        if url:
            await self._page.goto(url)
            
        await self._context.events.publish(RuntimeEvent("browser.launched", {}))

    async def close(self) -> None:
        if self._page:
            await self._page.close()
            self._page = None
        if self._browser_context:
            await self._browser_context.close()
            self._browser_context = None
        if self._browser:
            self._browser.remove_listener("disconnected", self._on_disconnected)
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        
        await self._context.events.publish(RuntimeEvent("browser.closed", {}))

    @property
    def page(self) -> Page | None:
        return self._page

    async def extract_naukri_jd(self, url: str) -> dict[str, str]:
        """Extracts job details specifically targeting Naukri.com structure."""
        if not self._page:
            raise RuntimeError("Browser not launched.")
        
        await self._page.goto(url, wait_until="domcontentloaded")
        # Give it a moment to load dynamic content
        await asyncio.sleep(2)
        
        # Simplified extraction logic for the prototype
        # On Naukri, job descriptions are often within elements having 'job-desc' or similar classes.
        # We will extract the full visible text and use the local LLM to parse it if needed,
        # or just grab standard selectors.
        
        title = await self._page.locator("h1").first.text_content() or "Unknown Title"
        company_loc = self._page.locator(".jd-header-comp-name a").first
        company = await company_loc.text_content() if await company_loc.count() > 0 else "Unknown Company"
        
        desc_loc = self._page.locator(".job-desc").first
        description = await desc_loc.text_content() if await desc_loc.count() > 0 else ""
        if not description:
            # Fallback to body text
            description = await self._page.locator("body").text_content() or ""
            
        return {
            "title": title.strip() if title else "",
            "company": company.strip() if company else "",
            "description": description.strip() if description else ""
        }


class BrowserPlugin:
    name = "browser"
    requires: tuple[str, ...] = ("ollama",)

    def __init__(self) -> None:
        self._service: BrowserService | None = None
        self._context: PluginContext | None = None

    async def start(self, context: PluginContext) -> None:
        self._context = context
        self._service = BrowserService(context)
        context.services.provide(BROWSER_SERVICE, self._service)

    async def stop(self) -> None:
        if self._service is not None:
            await self._service.close()
        if self._context is not None:
            self._context.services.remove(BROWSER_SERVICE)


def create_plugin() -> BrowserPlugin:
    return BrowserPlugin()
