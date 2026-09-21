"""Playwright browser plugin with stealth and LLM-assisted navigation."""

from __future__ import annotations

import asyncio
import logging
import threading
import concurrent.futures
from collections.abc import Callable
from pathlib import Path

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

    async def _launch_impl(self, url: str | None, win_x: int = 0, win_y: int = 0, win_w: int = 1280, win_h: int = 800) -> None:
        if self._browser_context is not None:
            if self._page is None or self._page.is_closed():
                self._page = await self._browser_context.new_page()
                stealth = Stealth()
                await stealth.apply_stealth_async(self._page)
            if url:
                await self._page.goto(url)
            return

        self._playwright = await async_playwright().start()
        profile_path = Path.home() / ".openclaw" / "browser_profile"
        profile_path.mkdir(parents=True, exist_ok=True)
        
        self._browser_context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_path),
            headless=False,
            viewport={"width": win_w, "height": win_h},
            args=[f"--window-position={win_x},{win_y}", f"--window-size={win_w},{win_h}"],
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        )
        self._browser_context.on("close", lambda ctx: self._on_disconnected(None))
        
        if self._browser_context.pages:
            self._page = self._browser_context.pages[0]
        else:
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
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def close(self) -> None:
        future = asyncio.run_coroutine_threadsafe(self._close_impl(), self._loop)
        await asyncio.wrap_future(future)

    async def _reset_session_impl(self) -> None:
        await self._close_impl()
        import shutil
        profile_path = Path.home() / ".openclaw" / "browser_profile"
        if profile_path.exists():
            shutil.rmtree(profile_path, ignore_errors=True)

    def reset_session(self) -> None:
        future = asyncio.run_coroutine_threadsafe(self._reset_session_impl(), self._loop)
        return future.result()

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

    async def _search_naukri_jobs_impl(self, role: str, location: str, max_results: int = 3, win_x: int = 0, win_y: int = 0, win_w: int = 1280, win_h: int = 800) -> list[str]:
        if not self._page or self._page.is_closed():
            await self._launch_impl(None, win_x, win_y, win_w, win_h)
            
        role_slug = role.replace(" ", "-").lower()
        loc_slug = location.replace(" ", "-").lower()
        url = f"https://www.naukri.com/{role_slug}-jobs-in-{loc_slug}"
        
        await self._page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(3) # Wait for page to render
        
        links = []
        locators = await self._page.locator("a.title").all()
        for loc in locators[:max_results]:
            href = await loc.get_attribute("href")
            if href:
                links.append(href)
        return links

    async def search_naukri_jobs(self, role: str, location: str, max_results: int = 3, win_x: int = 0, win_y: int = 0, win_w: int = 1280, win_h: int = 800) -> list[str]:
        future = asyncio.run_coroutine_threadsafe(self._search_naukri_jobs_impl(role, location, max_results, win_x, win_y, win_w, win_h), self._loop)
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
