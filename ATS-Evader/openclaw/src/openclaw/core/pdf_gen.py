"""Executive-tier PDF generation engine for Resumes and Cover Letters.

Uses Playwright Headless Chromium to compile styled HTML/CSS into ATS-optimized,
pixel-perfect PDFs with strict page-break controls and typography hierarchy.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import markdown  # type: ignore[import-untyped]
from playwright.async_api import async_playwright

RESUME_CSS = """
@page {
    size: A4;
    margin: 15mm 18mm 15mm 18mm;
}
* {
    box-sizing: border-box;
}
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    color: #1e293b;
    background: #ffffff;
    line-height: 1.48;
    font-size: 10pt;
    margin: 0;
    padding: 0;
    -webkit-font-smoothing: antialiased;
}

/* Header & Name */
h1 {
    font-size: 22pt;
    font-weight: 700;
    color: #0f172a;
    margin: 0 0 4px 0;
    text-align: center;
    letter-spacing: -0.02em;
}

/* Contact Bar / Subtitle directly below main heading */
h1 + p, .contact-bar {
    text-align: center;
    color: #475569;
    font-size: 9.5pt;
    margin: 0 0 14px 0;
    padding-bottom: 8px;
    border-bottom: 2px solid #e2e8f0;
}

/* Section Headings */
h2 {
    font-size: 11.5pt;
    font-weight: 700;
    color: #1e3a8a; /* Deep executive navy accent */
    text-transform: uppercase;
    letter-spacing: 0.06em;
    border-bottom: 1.5px solid #cbd5e1;
    padding-bottom: 3px;
    margin-top: 14px;
    margin-bottom: 6px;
    page-break-after: avoid;
    break-after: avoid;
}

/* Job Role / Degree / Project Headings */
h3 {
    font-size: 10.5pt;
    font-weight: 600;
    color: #0f172a;
    margin-top: 8px;
    margin-bottom: 2px;
    page-break-after: avoid;
    break-after: avoid;
}

/* Company, Dates, Location line */
h4 {
    font-size: 9.5pt;
    font-weight: 500;
    color: #475569;
    font-style: italic;
    margin-top: 1px;
    margin-bottom: 4px;
}

p {
    margin: 3px 0 5px 0;
    text-align: justify;
}

/* Bullet Points */
ul, ol {
    margin: 3px 0 6px 0;
    padding-left: 18px;
}

li {
    margin-bottom: 2.5px;
    line-height: 1.42;
    text-align: justify;
}

strong, b {
    font-weight: 600;
    color: #0f172a;
}

em, i {
    color: #334155;
}

/* Tables for skills, attributes or two-column details */
table {
    width: 100%;
    border-collapse: collapse;
    margin: 6px 0 10px 0;
    font-size: 9.5pt;
}

th, td {
    padding: 4px 8px;
    border: 1px solid #e2e8f0;
    vertical-align: top;
}

th {
    background-color: #f8fafc;
    font-weight: 600;
    color: #1e3a8a;
    text-align: left;
}

/* Strict Page Break Rules */
h1, h2, h3 {
    page-break-after: avoid;
    break-after: avoid;
}

li, p, tr {
    page-break-inside: avoid;
    break-inside: avoid;
}
"""

COVER_LETTER_CSS = """
@page {
    size: A4;
    margin: 20mm 22mm 20mm 22mm;
}
* {
    box-sizing: border-box;
}
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    color: #1e293b;
    background: #ffffff;
    line-height: 1.65;
    font-size: 11pt;
    margin: 0;
    padding: 0;
    -webkit-font-smoothing: antialiased;
}

/* Matching Branded Header */
.letterhead {
    border-bottom: 2px solid #1e3a8a;
    padding-bottom: 12px;
    margin-bottom: 24px;
}
.letterhead-name {
    font-size: 22pt;
    font-weight: 700;
    color: #0f172a;
    margin: 0 0 4px 0;
    letter-spacing: -0.02em;
}
.letterhead-contact {
    font-size: 9.5pt;
    color: #475569;
    line-height: 1.4;
}

/* Date and Recipient Section */
.meta-section {
    margin-bottom: 22px;
    font-size: 10pt;
    color: #334155;
}
.date-line {
    font-weight: 500;
    margin-bottom: 14px;
}
.recipient-block {
    line-height: 1.4;
}

/* Letter Content */
.letter-content p {
    margin: 0 0 14px 0;
    text-align: justify;
}

.letter-content strong {
    font-weight: 600;
    color: #0f172a;
}

/* Professional Sign-off */
.sign-off {
    margin-top: 28px;
    page-break-inside: avoid;
    break-inside: avoid;
}
.sign-off-salutation {
    margin-bottom: 36px;
}
.sign-off-name {
    font-weight: 700;
    color: #0f172a;
}
"""


class PdfGenerator:
    """Converts Markdown documents to executive-tier PDFs via Headless Chromium."""

    @staticmethod
    async def markdown_to_pdf(md_text: str, output_path: str, title: str = "Resume") -> str:
        """Converts Markdown resume text to an executive ATS-friendly PDF."""
        # Convert Markdown to HTML
        html_body = markdown.markdown(
            md_text,
            extensions=["tables", "fenced_code", "nl2br", "sane_lists"],
        )

        full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        {RESUME_CSS}
    </style>
</head>
<body>
    {html_body}
</body>
</html>
"""
        abs_output = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(abs_output), exist_ok=True)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_content(full_html, wait_until="load")
            await page.wait_for_timeout(100)

            await page.pdf(
                path=abs_output,
                format="A4",
                print_background=True,
                margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
            )
            await browser.close()

        return abs_output

    @staticmethod
    async def cover_letter_to_pdf(
        md_text: str,
        output_path: str,
        candidate_name: str | None = None,
        contact_info: str | None = None,
        recipient_info: str | None = None,
    ) -> str:
        """Converts cover letter Markdown text to an executive-styled PDF."""
        html_body = markdown.markdown(
            md_text,
            extensions=["tables", "fenced_code", "nl2br"],
        )

        now_str = datetime.now(UTC).strftime("%B %d, %Y")
        name_str = candidate_name or "Applicant"
        contact_str = contact_info or ""
        recipient_str = recipient_info or "Hiring Team"

        full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cover Letter - {name_str}</title>
    <style>
        {COVER_LETTER_CSS}
    </style>
</head>
<body>
    <div class="letterhead">
        <div class="letterhead-name">{name_str}</div>
        <div class="letterhead-contact">{contact_str}</div>
    </div>

    <div class="meta-section">
        <div class="date-line">{now_str}</div>
        <div class="recipient-block">
            <strong>To:</strong><br>
            {recipient_str}
        </div>
    </div>

    <div class="letter-content">
        {html_body}
    </div>

    <div class="sign-off">
        <div class="sign-off-salutation">Sincerely,</div>
        <div class="sign-off-name">{name_str}</div>
    </div>
</body>
</html>
"""
        abs_output = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(abs_output), exist_ok=True)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_content(full_html, wait_until="load")
            await page.wait_for_timeout(100)

            await page.pdf(
                path=abs_output,
                format="A4",
                print_background=True,
                margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
            )
            await browser.close()

        return abs_output
