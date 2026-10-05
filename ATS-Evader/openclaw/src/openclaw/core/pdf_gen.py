"""Executive-tier PDF generation engine for Resumes and Cover Letters.

Uses Playwright Headless Chromium to compile styled HTML/CSS into ATS-optimized,
pixel-perfect PDFs with strict page-break controls and typography hierarchy.
"""

from __future__ import annotations

import os
import re
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
    text-align: left;
}

/* Bullet Points */
ul, ol {
    margin: 3px 0 6px 0;
    padding-left: 18px;
}

li {
    margin-bottom: 3px;
    line-height: 1.45;
    text-align: left;
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


def sanitize_resume_markdown(md_text: str) -> str:
    """Pre-processes and normalizes LLM-generated resume markdown into executive-tier structure."""
    if not md_text:
        return ""

    raw_lines = md_text.splitlines()
    lines = [line.rstrip() for line in raw_lines]

    # Drop amateur sections: AVAILABILITY and REFERENCES
    skip_until_next_section = False
    filtered_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        upper = stripped.upper()
        if any(upper.startswith(junk) for junk in [
            "## AVAILABILITY", "AVAILABILITY", "### AVAILABILITY",
            "## REFERENCES", "REFERENCES", "### REFERENCES"
        ]):
            skip_until_next_section = True
            continue
        if skip_until_next_section:
            if re.match(r"^(?:#{1,3}\s+)?[A-Z\s]{4,}$", stripped):
                skip_until_next_section = False
            else:
                continue
        filtered_lines.append(line)

    lines = filtered_lines

    section_map = {
        "SUMMARY": "Professional Summary",
        "PROFESSIONAL SUMMARY": "Professional Summary",
        "EXECUTIVE SUMMARY": "Professional Summary",
        "TECHNICAL SKILLS": "Technical Skills",
        "SKILLS": "Technical Skills",
        "CORE COMPETENCIES": "Technical Skills",
        "PROFESSIONAL EXPERIENCE": "Professional Experience",
        "WORK EXPERIENCE": "Professional Experience",
        "EXPERIENCE": "Professional Experience",
        "EMPLOYMENT HISTORY": "Professional Experience",
        "KEY ARCHITECTURAL PROJECTS": "Key Projects",
        "ARCHITECTURAL PROJECTS": "Key Projects",
        "KEY PROJECTS": "Key Projects",
        "PROJECTS": "Key Projects",
        "EDUCATION": "Education",
        "ACADEMIC BACKGROUND": "Education",
        "CERTIFICATIONS": "Certifications",
        "CERTIFICATIONS & INTERESTS": "Certifications & Interests",
        "CERTIFICATIONS & LICENSES": "Certifications & Licenses",
    }

    def clean_hallucinations(text: str) -> str:
        return re.sub(r"\s*\((?:Applying for|Applicant|Targeting|Role:)[^\)]*\)", "", text, flags=re.IGNORECASE)

    cleaned_lines: list[str] = []
    i = 0
    in_experience = False
    in_skills = False

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            cleaned_lines.append("")
            i += 1
            continue

        stripped = clean_hallucinations(stripped)

        # 1. Candidate Name (first non-empty line)
        if not any(l.startswith("# ") for l in cleaned_lines) and len([l for l in cleaned_lines if l.strip()]) == 0:
            name = re.sub(r"^#+\s*", "", stripped)
            name_match = re.match(r"^([A-Z][a-zA-Z\.\s]+?)\s*[\–\—\-]\s*(.+)$", name)
            if name_match:
                candidate_name = name_match.group(1).strip()
                candidate_title = name_match.group(2).strip()
                cleaned_lines.append(f"# {candidate_name}")
                cleaned_lines.append(f"**{candidate_title}**")
            else:
                cleaned_lines.append(f"# {name}")
            i += 1
            continue

        # 2. Check for known section headings (with or without ##, with or without colons)
        clean_heading_key = re.sub(r"^#+\s*", "", stripped).strip().rstrip(":").upper()
        if clean_heading_key in section_map:
            std_title = section_map[clean_heading_key]
            cleaned_lines.append("")
            cleaned_lines.append(f"## {std_title}")
            in_experience = "Experience" in std_title
            in_skills = "Skills" in std_title
            i += 1
            continue

        # 3. Check for multi-line STAR pattern
        star_block: dict[str, str] = {}
        curr_idx = i
        while curr_idx < len(lines):
            curr_str = lines[curr_idx].strip()
            m = re.match(r"^[-*•]?\s*(Situation|Task|Action|Result)\s*:\s*(.+)$", curr_str, flags=re.IGNORECASE)
            if m:
                star_block[m.group(1).capitalize()] = m.group(2).strip()
                curr_idx += 1
            else:
                break

        if len(star_block) >= 2 and ("Action" in star_block or "Result" in star_block):
            action = star_block.get("Action", "")
            result = star_block.get("Result", "")
            situation = star_block.get("Situation", "")
            task = star_block.get("Task", "")

            bullet_parts = []
            if action:
                bullet_parts.append(action.rstrip("."))
            elif task:
                bullet_parts.append(task.rstrip("."))

            if result:
                res_clean = result.rstrip(".")
                if re.match(r"^(?:Reduced|Increased|Achieved|Slashing|Resulting|Delivered|Improved)", res_clean, flags=re.IGNORECASE):
                    bullet_parts.append(f", resulting in {res_clean[0].lower() + res_clean[1:]}")
                else:
                    bullet_parts.append(f"; {res_clean}")
            elif situation and not action:
                bullet_parts.append(f" ({situation})")

            unified_bullet = "".join(bullet_parts).strip()
            if not unified_bullet.endswith("."):
                unified_bullet += "."
            cleaned_lines.append(f"* {unified_bullet}")
            i = curr_idx
            continue

        # 4. Clean single bullets starting with Situation/Task/Action/Result labels
        single_star_m = re.match(r"^[-*•]?\s*(?:Situation|Task|Action|Result)\s*:\s*(.+)$", stripped, flags=re.IGNORECASE)
        if single_star_m:
            cleaned_lines.append(f"* {single_star_m.group(1).strip()}")
            i += 1
            continue

        # 5. Format skills category lines
        if in_skills:
            skill_m = re.match(r"^[-*•]?\s*([A-Za-z0-9\s/&]+)\s*:\s*(.+)$", stripped)
            if skill_m and not stripped.startswith("http"):
                cat_name = skill_m.group(1).strip()
                skills_val = skill_m.group(2).strip()
                cleaned_lines.append(f"* **{cat_name}:** {skills_val}")
                i += 1
                continue

        # 6. Format experience job titles & dates if plain text
        if in_experience:
            role_company_m = re.match(r"^([A-Z][a-zA-Z\s\(\)]+)\s*[\–\—\-]\s*([A-Za-z0-9\s\.,]+)$", stripped)
            date_m = re.match(r"^([A-Za-z]+\s*\d{4}\s*[\–\—\-]\s*(?:Present|[A-Za-z]+\s*\d{4}))(?:\s*\|\s*(.+))?$", stripped)

            if role_company_m and not stripped.startswith("#") and not stripped.startswith("*") and not stripped.startswith("-"):
                cleaned_lines.append("")
                cleaned_lines.append(f"### {stripped}")
                i += 1
                continue
            elif date_m and not stripped.startswith("#"):
                cleaned_lines.append(f"#### {stripped}")
                i += 1
                continue

        # 7. Standard lines
        if stripped.startswith("- "):
            cleaned_lines.append(f"* {stripped[2:]}")
        else:
            cleaned_lines.append(stripped)
        i += 1

    return "\n".join(cleaned_lines).strip()


class PdfGenerator:
    """Converts Markdown documents to executive-tier PDFs via Headless Chromium."""

    @staticmethod
    async def markdown_to_pdf(md_text: str, output_path: str, title: str = "Resume") -> str:
        """Converts Markdown resume text to an executive ATS-friendly PDF."""
        # Sanitize and normalize LLM markdown before HTML compilation
        sanitized_md = sanitize_resume_markdown(md_text)

        # Convert Markdown to HTML
        html_body = markdown.markdown(
            sanitized_md,
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
