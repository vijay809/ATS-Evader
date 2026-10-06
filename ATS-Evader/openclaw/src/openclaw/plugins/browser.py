"""Playwright browser plugin with stealth and LLM-assisted navigation."""

from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
from playwright_stealth import Stealth  # type: ignore[import-untyped]

from openclaw.plugins.manager import PluginContext
from openclaw.plugins.ollama import OllamaClient
from openclaw.plugins.semantic_navigator import SemanticNavigator

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

    def _on_disconnected(self, browser: Any = None) -> None:
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
            channel="chrome",
            headless=False,
            viewport={"width": win_w, "height": win_h},
            args=[
                f"--window-position={win_x},{win_y}", 
                f"--window-size={win_w},{win_h}",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars"
            ],
            ignore_default_args=["--enable-automation"],
        )
        self._browser_context.on("close", lambda ctx: self._on_disconnected(None))
        
        def handle_new_page(new_page: Page) -> None:
            self._page = new_page
            
        self._browser_context.on("page", handle_new_page)
        
        if self._browser_context.pages:
            self._page = self._browser_context.pages[-1]
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

    @staticmethod
    def _extract_company_from_url(url: str, title: str = "") -> str | None:
        if not url:
            return None
        import re
        import urllib.parse
        path = urllib.parse.urlparse(url).path
        slug = path.rstrip("/").split("/")[-1]
        if not slug.startswith("job-listings-"):
            return None
        
        body = slug[len("job-listings-"):]
        body = re.sub(r'-\d{8,}$', '', body)
        body = re.sub(r'-\d+-to-\d+-years.*$', '', body, flags=re.IGNORECASE)
        
        loc_tokens = [
            "noida", "greater-noida", "gurgaon", "gurugram", "bangalore", "bengaluru",
            "hyderabad", "secunderabad", "pune", "mumbai", "navi-mumbai", "chennai",
            "delhi-ncr", "delhi", "new-delhi", "kolkata", "ahmedabad", "chandigarh",
            "jaipur", "remote", "india"
        ]
        changed = True
        while changed:
            changed = False
            for loc in loc_tokens:
                if body.lower().endswith(f"-{loc}"):
                    body = body[:-len(loc)-1]
                    changed = True
                    
        if title:
            norm_title = re.sub(r'[^a-zA-Z0-9]+', '-', title).strip('-').lower()
            if body.lower().startswith(norm_title):
                company_part = body[len(norm_title):].strip('-')
                if company_part:
                    return company_part.replace('-', ' ').title()
            title_words = [w for w in re.split(r'[^a-zA-Z0-9]+', title.lower()) if len(w) > 2]
            body_words = body.split('-')
            matched_idx = 0
            for i, bw in enumerate(body_words):
                if any(tw in bw.lower() for tw in title_words):
                    matched_idx = i + 1
                else:
                    break
            if 0 < matched_idx < len(body_words):
                company_part = '-'.join(body_words[matched_idx:])
                if company_part:
                    return company_part.replace('-', ' ').title()
                    
        return body.replace('-', ' ').title() if body else None

    async def _extract_naukri_jd_impl(self, url: str) -> dict[str, str]:
        if not self._page or self._page.is_closed():
            raise RuntimeError("Browser not launched or page is closed.")
        
        await self._page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(2)
        
        import json
        import re

        # 1. Title Extraction
        title = ""
        for sel in ["h1", "[class*='jd-header-title']", "header h1", "h1[title]"]:
            loc = self._page.locator(sel)
            if await loc.count() > 0:
                txt = await loc.first.text_content()
                if txt and txt.strip():
                    title = txt.strip()
                    break

        # 2. Company Extraction
        company = ""
        # Multi-tiered selector checks for modern Naukri CSS Modules and standard layouts
        company_selectors = [
            "[class*='jd-header-comp-name'] a",
            "[class*='comp-name'] a",
            "a[title*='Careers']",
            "a[href*='jobs-careers']",
            "section[id='job_header'] [class*='comp-name'] a",
            "[class*='jd-header-comp-name']",
            "[class*='comp-name']",
            "h2[title]",  # from About the company
            ".jd-header-comp-name a",
            ".comp-name",
        ]
        for sel in company_selectors:
            loc = self._page.locator(sel)
            if await loc.count() > 0:
                txt = await loc.first.text_content()
                if txt and txt.strip() and not txt.strip().startswith("Send me"):
                    clean = txt.strip().split("\n")[0].strip()
                    clean = re.sub(r'\d+\.\d+.*$', '', clean).strip()
                    if clean and len(clean) > 1:
                        company = clean
                        break

        # Logo alt fallback
        if not company:
            logo_loc = self._page.locator("img[alt*='logo'], img[alt*='Logo']").first
            if await logo_loc.count() > 0:
                alt = await logo_loc.get_attribute("alt")
                if alt:
                    clean_alt = re.sub(r'\s*logo\s*', '', alt, flags=re.IGNORECASE).strip()
                    if clean_alt:
                        company = clean_alt

        # JSON-LD scripts extraction
        if not company or not title:
            scripts = await self._page.locator("script[type='application/ld+json']").all()
            for s in scripts:
                c = await s.text_content()
                if c:
                    try:
                        data = json.loads(c)
                        if isinstance(data, dict):
                            if not title and data.get("title"):
                                title = data["title"].strip()
                            h_org = data.get("hiringOrganization")
                            if isinstance(h_org, dict) and h_org.get("name"):
                                company = h_org["name"].strip()
                                break
                            elif isinstance(h_org, str) and h_org.strip():
                                company = h_org.strip()
                                break
                            if not company and isinstance(data.get("identifier"), dict):
                                ident_name = data.get("identifier", {}).get("name")
                                if ident_name and ident_name.strip():
                                    company = ident_name.strip()
                                    break
                    except Exception:
                        pass

        # 3. Description Extraction
        desc_selectors = [
            "[class*='dang-inner-html']",
            "[class*='job-desc-container']",
            "[class*='job-desc']",
            ".job-desc",
        ]
        description = ""
        for sel in desc_selectors:
            loc = self._page.locator(sel)
            if await loc.count() > 0:
                txt = await loc.first.text_content()
                if txt and txt.strip():
                    description = txt.strip()
                    break

        if not description:
            description = (await self._page.locator("body").text_content() or "").strip()

        # If description contains embedded JSON-LD string but company was missed, try parsing
        if (not company or company == "Unknown Company") and description and '{"@context"' in description:
            start = description.find('{"@context"')
            if start != -1:
                depth = 0
                in_string = False
                escape = False
                end = -1
                for i in range(start, len(description)):
                    char = description[i]
                    if escape:
                        escape = False
                        continue
                    if char == '\\':
                        escape = True
                        continue
                    if char == '"':
                        in_string = not in_string
                        continue
                    if not in_string:
                        if char == '{':
                            depth += 1
                        elif char == '}':
                            depth -= 1
                            if depth == 0:
                                end = i + 1
                                break
                if end != -1:
                    try:
                        d = json.loads(description[start:end])
                        if not title and d.get("title"):
                            title = d["title"].strip()
                        if isinstance(d.get("hiringOrganization"), dict) and d["hiringOrganization"].get("name"):
                            company = d["hiringOrganization"]["name"].strip()
                        elif isinstance(d.get("identifier"), dict) and d["identifier"].get("name"):
                            company = d["identifier"]["name"].strip()
                    except Exception:
                        pass

        # URL slug fallback if still not found
        if not company or company == "Unknown Company":
            parsed_company = BrowserService._extract_company_from_url(url, title)
            if parsed_company:
                company = parsed_company

        clean_title = re.sub(r"\s+", " ", title).strip() if title else "Unknown Title"
        clean_company = re.sub(r"\s+", " ", company).strip() if company else "Unknown Company"
        clean_desc = description.strip() if description else ""

        return {
            "title": clean_title,
            "company": clean_company,
            "description": clean_desc,
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
        
        if self._page is None:
            raise RuntimeError("Browser page failed to initialize")

        await self._page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(3) # Wait for page to render
        
        links = []
        # Support standard a.title and modern CSS-module variant locators
        locators = await self._page.locator("a.title, a[class*='title'], [class*='srp-jobtuple'] a[class*='title']").all()
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
