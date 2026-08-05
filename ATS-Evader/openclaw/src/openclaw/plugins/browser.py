"""Playwright browser plugin with stealth and LLM-assisted navigation."""

from __future__ import annotations

import asyncio
import logging
import threading
import concurrent.futures
from collections.abc import Callable

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
from playwright_stealth import Stealth  # type: ignore[import-untyped]

from openclaw.core.events import RuntimeEvent
from openclaw.plugins.manager import PluginContext
from openclaw.plugins.semantic_navigator import SemanticNavigator
from openclaw.plugins.ollama import OllamaClient

logger = logging.getLogger(__name__)

BROWSER_SERVICE = "browser.agent"


class BrowserService:
    def __init__(self, context: PluginContext) -> None:
        self._context = context
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._browser_context: BrowserContext | None = None
        self._page: Page | None = None
        
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _on_disconnected(self, browser: Browser) -> None:
        self._page = None
        self._browser_context = None
        self._browser = None

    async def _launch_impl(self, url: str | None) -> None:
        if self._browser is not None and not self._browser.is_connected():
            self._page = None
            self._browser_context = None
            self._browser = None
            
        if self._browser is not None:
            if self._page is None or self._page.is_closed():
                if self._browser_context is None:
                    # fallback if context was lost
                    self._browser_context = await self._browser.new_context(
                        viewport={"width": 1280, "height": 800},
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                    )
                self._page = await self._browser_context.new_page()
                stealth = Stealth()
                await stealth.apply_stealth_async(self._page)
                
            if url:
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
        stealth = Stealth()
        await stealth.apply_stealth_async(self._page)
        
        if url:
            await self._page.goto(url)

    async def launch(self, url: str | None = None) -> None:
        future = asyncio.run_coroutine_threadsafe(self._launch_impl(url), self._loop)
        await asyncio.wrap_future(future)

    async def _close_impl(self) -> None:
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

    async def close(self) -> None:
        future = asyncio.run_coroutine_threadsafe(self._close_impl(), self._loop)
        await asyncio.wrap_future(future)

    @property
    def page(self) -> Page | None:
        return self._page

    async def _extract_naukri_jd_impl(self, url: str) -> dict[str, str]:
        if not self._page or self._page.is_closed():
            raise RuntimeError("Browser not launched or page is closed.")
        
        await self._page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(2)
        
        title = await self._page.locator("h1").first.text_content() or "Unknown Title"
        company_loc = self._page.locator(".jd-header-comp-name a").first
        company = await company_loc.text_content() if await company_loc.count() > 0 else "Unknown Company"
        
        desc_loc = self._page.locator(".job-desc").first
        description = await desc_loc.text_content() if await desc_loc.count() > 0 else ""
        if not description:
            description = await self._page.locator("body").text_content() or ""
            
        return {
            "title": title.strip() if title else "",
            "company": company.strip() if company else "",
            "description": description.strip() if description else ""
        }

    async def extract_naukri_jd(self, url: str) -> dict[str, str]:
        future = asyncio.run_coroutine_threadsafe(self._extract_naukri_jd_impl(url), self._loop)
        return await asyncio.wrap_future(future)

    def stop_thread(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=2.0)


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
        
        ollama_client = context.services.get("ollama.client")
        if not isinstance(ollama_client, OllamaClient):
            raise TypeError("OllamaClient is required")
            
        self._navigator = SemanticNavigator(ollama_client, self._service)
        context.services.provide("browser.navigator", self._navigator)

    async def stop(self) -> None:
        if self._service is not None:
            await self._service.close()
            self._service.stop_thread()
        if self._context is not None:
            self._context.services.remove("browser.navigator")
            self._context.services.remove(BROWSER_SERVICE)


def create_plugin() -> BrowserPlugin:
    return BrowserPlugin()
