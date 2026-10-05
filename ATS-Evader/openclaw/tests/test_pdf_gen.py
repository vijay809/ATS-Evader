from openclaw.core.pdf_gen import sanitize_resume_markdown


def test_sanitize_resume_markdown_promotes_headings_and_cleans_hallucinations() -> None:
    raw_md = """Vijay Kumar Srivastava
Senior Software Engineer – Tech Lead (Applying for Blazor Role)
Noida | +91-9807969454 | vijay.kr809@gmail.com | LinkedIn | GitHub

PROFESSIONAL SUMMARY
Forward-thinking Senior Software Engineer with 5+ years of experience in component-based front-end architecture.

TECHNICAL SKILLS
Languages: JavaScript (ES6+), TypeScript, Python
Frontend: React, React Native, HTML5, CSS3, Redux, Context API
Backend: Node.js, Django

PROFESSIONAL EXPERIENCE
Senior Software Engineer – Ksolves India Ltd., Noida, Uttar Pradesh
December 2024 – Present
- Situation: Greenfield Insurance module for an enterprise building management system (NDA).
- Task: Architect and deliver a scalable, high-performance front-end.
- Action: Designed component-based architecture, separated global Redux state from local Context API, modularized UI, led a 4-engineer pod, enforced >80% automated test coverage.
- Result: Reduced Largest Contentful Paint from 8s to 2s and Interaction to Next Paint from 1500ms to <100ms.

AVAILABILITY
Open to relocation and flexible working hours.

REFERENCES
Available upon request.
"""
    sanitized = sanitize_resume_markdown(raw_md)

    # 1. Candidate Name and Title
    assert "# Vijay Kumar Srivastava" in sanitized
    assert "Senior Software Engineer" in sanitized
    assert "(Applying for Blazor Role)" not in sanitized

    # 2. Promoted Headings
    assert "## Professional Summary" in sanitized
    assert "## Technical Skills" in sanitized
    assert "## Professional Experience" in sanitized

    # 3. STAR bullet synthesis
    assert "Designed component-based architecture" in sanitized
    assert "resulting in reduced Largest Contentful Paint" in sanitized
    assert "- Situation:" not in sanitized
    assert "- Task:" not in sanitized
    assert "- Action:" not in sanitized
    assert "- Result:" not in sanitized

    # 4. Amateur sections stripped
    assert "AVAILABILITY" not in sanitized
    assert "REFERENCES" not in sanitized
    assert "Available upon request" not in sanitized


def test_sanitize_resume_markdown_handles_already_clean_markdown() -> None:
    clean_md = """# Jane Doe
San Francisco, CA | jane@example.com

## Professional Summary
Experienced Engineering Leader.

## Professional Experience
### Lead Engineer — TechCorp
#### Jan 2021 – Present | San Francisco, CA
* Spearheaded distributed microservices refactor, improving system throughput by 40%.
"""
    result = sanitize_resume_markdown(clean_md)
    assert "# Jane Doe" in result
    assert "## Professional Summary" in result
    assert "## Professional Experience" in result
    assert "Spearheaded distributed microservices refactor" in result
