import asyncio
import pytest
from openclaw.plugins.browser import BrowserService


def test_extract_company_from_url():
    url1 = "https://www.naukri.com/job-listings-senior-software-engineer-globallogic-noida-5-to-10-years-061026012964"
    assert BrowserService._extract_company_from_url(url1, "Senior Software Engineer") == "Globallogic"

    url2 = "https://www.naukri.com/job-listings-technical-lead-infinite-computer-solutions-india-pvt-ltd-noida-5-to-7-years-180926504648"
    assert BrowserService._extract_company_from_url(url2, "Technical Lead") == "Infinite Computer Solutions India Pvt Ltd"

    url3 = "https://www.naukri.com/job-listings-senior-software-engineer-barco-electronic-systems-ltd-noida-6-to-9-years-050826505174"
    assert BrowserService._extract_company_from_url(url3, "Senior Software Engineer") == "Barco Electronic Systems Ltd"

    url4 = "https://www.naukri.com/job-listings-esm-tech-lead-hexaware-technologies-noida-5-to-7-years-290526503396"
    assert BrowserService._extract_company_from_url(url4, "ESM Tech Lead") == "Hexaware Technologies"


@pytest.mark.asyncio
async def test_extract_naukri_globallogic_html():
    from playwright.async_api import async_playwright

    html = """
    <div class="styles_jhc__top__BUxpc">
        <div class="styles_jhc__jd-top-head__MFoZl">
            <header><h1 class="styles_jd-header-title__rZwM1" title="Senior Software Engineer">Senior Software Engineer</h1></header>
            <div class="styles_jd-header-comp-name__MvqAI">
                <a href="https://www.naukri.com/globallogic-jobs-careers-2937?src=jddesktop" target="_blank" title="Globallogic Careers">Globallogic</a>
            </div>
        </div>
    </div>
    <div class="styles_short-desc__8IUp6">
        <div class="styles_JDC__dang-inner-html__h0K4t">
            <b>Description:</b> Join GlobalLogic to build distributed systems.
        </div>
    </div>
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        # Mock goto so it does not navigate away from our set_content
        original_goto = page.goto
        page.goto = lambda *args, **kwargs: asyncio.sleep(0.01)
        await page.set_content(html)

        # Mock BrowserService with this page
        class DummyService:
            _page = page
            _extract_company_from_url = BrowserService._extract_company_from_url
            _extract_naukri_jd_impl = BrowserService._extract_naukri_jd_impl

        dummy = DummyService()
        result = await dummy._extract_naukri_jd_impl("https://www.naukri.com/job-listings-test")
        await browser.close()

        assert result["title"] == "Senior Software Engineer"
        assert result["company"] == "Globallogic"
        assert "Join GlobalLogic" in result["description"]
