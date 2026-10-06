"""Local, structured ATS resume analysis capability."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from openclaw.plugins.manager import PluginContext
from openclaw.plugins.ollama import OLLAMA_CLIENT_SERVICE, OllamaClient

logger = logging.getLogger(__name__)

ATS_ANALYZER_SERVICE = "ats.analyzer"


def clean_favoring_points(raw_items: list[str]) -> list[str]:
    """Extracts concise, purely positive alignment points with zero negative caveats."""
    negative_patterns = [
        r"\bhowever\b",
        r"\bcritical gaps?\b",
        r"\bmajor blocker\b",
        r"\blacks?\b",
        r"\blacking\b",
        r"\bmissing\b",
        r"\bdoes not (?:have|possess|substantiate|contain|explicitly)\b",
        r"\bno explicit\b",
        r"\bmust explicitly\b",
        r"\bnot found\b",
        r"\bunsupported\b",
        r"\bto be considered a strong match\b",
        r"\brequires\b",
        r"\bgap\b",
    ]

    cleaned: list[str] = []

    for raw in raw_items:
        if not raw or not raw.strip():
            continue
        # Split into individual sentences
        sentences = re.split(r"(?<=[.!?])\s+", raw.strip())
        for s in sentences:
            s = s.strip()
            if not s:
                continue

            # If sentence has a contrast conjunction like "but lacks", take only the positive leading clause
            contrast_match = re.search(
                r"^(.*?)(?:\s*,\s*|\s+)(?:but\s+lacks?\b|however\b|although\s+lacking\b|yet\s+lacks?\b|while\s+lacking\b)",
                s,
                re.IGNORECASE,
            )
            if contrast_match:
                s = contrast_match.group(1).strip()

            # Check if this sentence contains any negative words or requirement caveats
            if any(re.search(pat, s, re.IGNORECASE) for pat in negative_patterns):
                continue

            # Strip conditional qualifiers like "If the role is flexible,"
            s = re.sub(r"^(?:if the role is flexible,\s*)", "", s, flags=re.IGNORECASE)

            # Strip common boilerplate lead-ins
            s = re.sub(
                r"^(?:the\s+)?candidate(?:'s)?\s+(?:is\s+a\s+highly\s+experienced\s+[^,]+with\s+|has\s+|is\s+a\s+|is\s+|possesses\s+)?",
                "",
                s,
                flags=re.IGNORECASE,
            )
            s = re.sub(r"^(?:the\s+)?seniority\s+and\s+", "", s, flags=re.IGNORECASE)

            # Strip trailing repetitive filler like "to the ... component"
            s = s.rstrip(".").strip()
            s = re.sub(r"\s+to the [a-zA-Z0-9/\s]+ component$", "", s, flags=re.IGNORECASE)

            # Check for compound sentence with "including demonstrable experience with" / "including experience with"
            inc_match = re.search(r"^(.*?),\s*including\s+(?:demonstrable\s+)?experience\s+with\s+(.*)$", s, re.IGNORECASE)
            if inc_match:
                part1 = inc_match.group(1).strip()
                part2 = "Experience with " + inc_match.group(2).strip()
                for p in [part1, part2]:
                    p = p.rstrip(".").strip()
                    if len(p) > 10:
                        cleaned.append(p[0].upper() + p[1:])
                continue

            if len(s) > 10:
                cleaned.append(s[0].upper() + s[1:])

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_items: list[str] = []
    for item in cleaned:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            unique_items.append(item)

    return unique_items


def club_missing_skills(skills: list[str]) -> list[str]:
    """Clubs missing skills by technology families or comma-separates them into compact lines."""
    if not skills:
        return []

    # Flatten any comma-separated inputs first
    flat_skills: list[str] = []
    for s in skills:
        if not s:
            continue
        # Split by comma if not inside parentheses
        parts = re.split(r",\s*(?![^()]*\))", s.strip())
        for p in parts:
            p_clean = p.strip()
            if p_clean and p_clean not in flat_skills:
                flat_skills.append(p_clean)

    # Defined technology clusters
    clusters: list[tuple[str, list[str]]] = [
        (".NET & Microsoft", [r"(?:\.net|c#|asp\.net|blazor|wpf|entity framework|\bef\b)"]),
        ("Cloud & Infra", [r"(?:azure|aws|gcp|cloud|terraform|lambda|cloudformation)"]),
        ("Databases & Caching", [r"(?:sql|postgres|mysql|cosmos|redis|mongodb|oracle|cassandra|dynamodb)"]),
        ("Containers & DevOps", [r"(?:docker|kubernetes|k8s|helm|jenkins|ci/cd|ansible|terraform|argocd)"]),
        ("Frontend & UI", [r"(?:react|angular|vue|typescript|javascript|next\.js|html|css|tailwind|svelte)"]),
        ("Backend & Languages", [r"(?:python|java|golang|\bgo\b|rust|c\+\+|node|express|fastapi|django|flask|spring)"]),
        ("Messaging & Streaming", [r"(?:kafka|rabbitmq|activemq|sqs|event grid|service bus)"]),
        ("AI / ML", [r"(?:langchain|llm|pytorch|tensorflow|openai|nlp|rag|huggingface)"]),
    ]

    used: set[str] = set()
    grouped_result: list[str] = []

    for cluster_name, patterns in clusters:
        cluster_items: list[str] = []
        for s in flat_skills:
            if s in used:
                continue
            if any(re.search(pat, s, re.IGNORECASE) for pat in patterns):
                cluster_items.append(s)
                used.add(s)
        if cluster_items:
            grouped_result.append(", ".join(cluster_items))

    # Remaining skills that did not match any cluster
    remaining = [s for s in flat_skills if s not in used]
    # Chunk remaining in groups of 2-3
    for i in range(0, len(remaining), 3):
        chunk = remaining[i : i + 3]
        grouped_result.append(", ".join(chunk))

    return grouped_result


class AtsAnalysis(BaseModel):
    match_score: int = Field(ge=0, le=100)
    matched_keywords: list[str]
    missing_keywords: list[str]
    recommendations: list[str]
    summary: str
    favoring_points: list[str] = Field(default_factory=list)
    unsupported_details: list[str] = Field(default_factory=list)
    missing_core_skills: list[str] = Field(default_factory=list)
    formatting_risks: list[str] = Field(default_factory=list)


class EligibilityFacts(BaseModel):
    min_years_experience: int | None
    location_type: str | None


class ParsedResumeData(BaseModel):
    preferences: dict[str, str]
    structured_json: str


class TailoredResume(BaseModel):
    tailored_resume: str
    change_summary: list[str]
    warnings: list[str]


class CoverLetter(BaseModel):
    cover_letter: str
    warnings: list[str]


class AtsAnalysisError(RuntimeError):
    """The local model response could not be interpreted as an ATS analysis."""


class AtsAnalyzer:
    def __init__(self, client: OllamaClient) -> None:
        self._client = client

    async def analyze(
        self,
        resume: str,
        job_description: str,
        *,
        model: str | None = None,
    ) -> AtsAnalysis:
        if not resume.strip() or not job_description.strip():
            raise ValueError("Both resume and job description are required")
        prompt = self._build_prompt(resume, job_description)
        
        for attempt in range(3):
            completion = await self._client.generate(
                prompt,
                model=model,
                format="json",
                temperature=0.1,
                system="You are an expert ATS (Applicant Tracking System) auditor and recruitment analyst. You strictly evaluate resume-to-job alignment without hallucinations.",
            )
            try:
                return self._parse_analysis(completion.text)
            except AtsAnalysisError as error:
                if attempt == 2:
                    raise
                logger.warning(f"Failed to parse ATS analysis on attempt {attempt + 1}: {error}")
                prompt += f"\n\nYour previous response was invalid: {error}. Please fix it and return ONLY valid JSON matching the exact schema."
        raise AtsAnalysisError("Failed to generate valid ATS analysis after retries")

    async def check_eligibility(self, job_description: str, model: str | None = None) -> EligibilityFacts:
        if not job_description.strip():
            raise ValueError("Job description is required")
            
        prompt = f"""You are a fast data extractor. Read this job description and extract ONLY the strict requirements.
Do not invent anything. If a requirement is not explicitly stated, return null.
Return only valid JSON with this exact schema:
{{
  "min_years_experience": integer (e.g. if it says 3-5 years, return 3), or null if not specified,
  "location_type": string (must be exactly one of: "Remote", "On-site", "Hybrid"), or null if not specified
}}

Job description:
---
{job_description}
---"""
        for attempt in range(3):
            completion = await self._client.generate(
                prompt,
                model=model,
                format="json",
                temperature=0.0,
                system="You are a precise data extractor. Extract only explicit factual requirements from the job description.",
            )
            try:
                parsed_dict = AtsAnalyzer._parse_json(completion.text)
                return EligibilityFacts.model_validate(parsed_dict)
            except (AtsAnalysisError, ValueError) as error:
                if attempt == 2:
                    raise
                logger.warning(f"Failed to parse eligibility facts on attempt {attempt + 1}: {error}")
                prompt += f"\n\nYour previous response was invalid: {error}. Please fix it and return ONLY valid JSON matching the exact schema."
        raise AtsAnalysisError("Failed to generate valid Eligibility Facts after retries")

    async def tailor(
        self,
        resume: str,
        job_description: str,
        *,
        model: str | None = None,
    ) -> TailoredResume:
        if not resume.strip() or not job_description.strip():
            raise ValueError("Both resume and job description are required")
        prompt = self._build_tailoring_prompt(resume, job_description)
        
        for attempt in range(3):
            completion = await self._client.generate(
                prompt,
                model=model,
                format="json",
                temperature=0.2,
                system="You are an executive resume writer and ATS optimization strategist. You craft high-impact resumes where every achievement bullet begins with an active verb and includes quantifiable metrics. NEVER output literal labels like Situation, Task, Action, or Result.",
            )
            try:
                return self._parse_tailoring(completion.text)
            except AtsAnalysisError as error:
                if attempt == 2:
                    raise
                logger.warning(f"Failed to parse Tailored resume on attempt {attempt + 1}: {error}")
                prompt += f"\n\nYour previous response was invalid: {error}. Please fix it and return ONLY valid JSON matching the exact schema."
        raise AtsAnalysisError("Failed to generate valid Tailored resume after retries")

    @staticmethod
    def _build_prompt(resume: str, job_description: str) -> str:
        return f"""Compare the candidate's resume against the job description with calibrated scoring and a thorough Gap & Flag audit:

EVALUATION WEIGHTS:
1. Role & Seniority Match (30%): If the seniority level clashes (e.g., Senior applying for Junior/Intern or vice versa), cap total score at 20% max regardless of skill overlap.
2. Core Technical Skills & Tooling (40%): Overlap between explicitly mentioned tech stack in the JD and candidate's hands-on experience.
3. Domain & Functional Experience (20%): Relevance of industry background and problem domain.
4. Education, Certifications & Credentials (10%).

GAP & FLAG AUDIT DIRECTIVES:
- favoring_points: 3 to 5 concise bullet points highlighting strong candidate alignment, matching qualifications, or relevant experience. MUST BE PURELY POSITIVE (NO negative caveats, NO "however", NO mentions of lacking skills or blockers). Communicate concisely with fewer words (e.g. ["Strong proficiency in modern frontend and Python backend", "Experience with Generative AI via LangChain", "Functional domain (Enterprise Systems) aligns well"]).
- missing_core_skills: Hard technical skills, frameworks, languages, or tools strictly required in the JD that the candidate does not appear to have in the resume. Group closely related technologies into comma-separated items or clubbed categories (e.g. [".NET, C#, ASP.NET Core", "SQL Server, Cosmos DB, Redis", "Docker, Kubernetes"]).
- unsupported_details: Qualifications, domain specializations, years of experience, or responsibilities demanded by the JD that the candidate's resume cannot substantiate or verify (e.g. ['Requires 5+ years in Healthcare domain', 'Requires cloud microservice ownership']).
- formatting_risks: Potential ATS parsing vulnerabilities, missing standard skill synonyms/acronyms, or structural formatting risks that might cause automated rejection.

Return ONLY valid JSON with this exact schema:
{{
  "match_score": integer from 0 to 100,
  "matched_keywords": [string],
  "missing_keywords": [string],
  "favoring_points": [string],
  "missing_core_skills": [string],
  "unsupported_details": [string],
  "formatting_risks": [string],
  "recommendations": [string],
  "summary": string
}}

Resume:
---
{resume}
---

Job description:
---
{job_description}
---"""

    @staticmethod
    def _build_tailoring_prompt(resume: str, job_description: str) -> str:
        return f"""You are an elite executive resume writer and ATS optimization strategist. Tailor the candidate's master resume for the provided job description with maximum ATS keyword synergy while remaining 100% truthful.

STRICT TAILORING DIRECTIVES:
1. ZERO FABRICATION: Never invent qualifications, employers, degrees, dates, tools, or metrics not grounded in the master resume. If a JD requirement cannot be satisfied truthfully, record it in warnings.
2. ATS KEYWORD ALIGNMENT: Seamlessly re-frame existing achievements to adopt the exact terminology and phrasing found in the job description.
3. EXECUTIVE BULLET FORMATTING:
   - Every bullet in Professional Experience MUST begin with a strong past-tense action verb (e.g., "Architected", "Engineered", "Optimized", "Spearheaded", "Led").
   - Frame accomplishments with quantifiable outcomes and metrics (e.g., latency, throughput, team velocity, test coverage).
   - NEVER output the literal words "Situation:", "Task:", "Action:", or "Result:" in bullet points or anywhere in the resume. Combine context, action, and metrics into a single cohesive bullet point.
4. CLEAN STRUCTURE & ZERO HALLUCINATIONS IN HEADINGS:
   - Line 1 MUST be `# Full Name` (e.g., `# Vijay Kumar Srivastava`). NEVER append parentheticals, notes, or role tags like "(Applying for ...)" or "(Tech Lead)".
   - Line 2 MUST be the target professional title (e.g., `Senior Software Engineer`).
   - Line 3 MUST be contact information (e.g., `City, State | Phone | Email | LinkedIn | GitHub`).
   - Use standard markdown headings: `## Professional Summary`, `## Technical Skills`, `## Professional Experience`, `## Key Projects`, `## Education`.
   - In Technical Skills, group skills cleanly: `* **Category:** Skill 1, Skill 2, Skill 3`.
   - In Professional Experience, format roles as:
     `### Job Title — Company Name`
     `#### Month Year – Month Year | City, State`
   - NEVER include sections for "References", "Availability", or "Objective".

<JOB_DESCRIPTION>
{job_description}
</JOB_DESCRIPTION>

<MASTER_RESUME>
{resume}
</MASTER_RESUME>

Respond ONLY with valid JSON matching this exact schema:
{{
  "tailored_resume": "Full tailored resume in clean executive Markdown matching the instructions above",
  "change_summary": ["List of specific adjustments and keyword additions made"],
  "warnings": ["Any hard requirements from the JD that could not be satisfied truthfully"]
}}"""

    def tailor_resume(self, master_resume: str, job_description: str, model_id: str | None = None) -> TailoredResume:
        prompt = self._build_tailoring_prompt(master_resume, job_description)
        import asyncio
        response = asyncio.run(
            self._client.generate(
                prompt,
                model=model_id,
                format="json",
                temperature=0.2,
                system="You are an executive resume writer and ATS optimization strategist. You craft high-impact resumes where every achievement bullet begins with an active verb and includes quantifiable metrics. NEVER output literal labels like Situation, Task, Action, or Result.",
            )
        )
        try:
            parsed_dict = AtsAnalyzer._parse_json(response.text)
            return TailoredResume.model_validate(parsed_dict)
        except Exception as e:
            logger.error(f"Failed to parse tailored resume: {response.text}")
            raise AtsAnalysisError("Invalid tailor response from model") from e

    def generate_cover_letter(self, master_resume: str, job_description: str, model_id: str | None = None) -> CoverLetter:
        prompt = f"""Write an executive, persuasive cover letter bridging the candidate's verified experience with the company's specific needs.

COVER LETTER RULES:
1. HIGH-IMPACT HOOK: Start directly with a compelling thesis statement highlighting the candidate's relevant background and immediate value proposition. NEVER use generic openings like "I am writing to express my interest in..." or "Enclosed please find my resume".
2. PAIN-POINT MAPPING: In 2-3 body paragraphs, connect 2 major challenges described in the job description to concrete achievements from the master resume.
3. TONE: Confident, collaborative, concise, executive.
4. HONESTY: Do not invent projects or skills.
5. FORMATTING: Return clean Markdown with paragraphs. Do not wrap the JSON response in code fences.

<JOB_DESCRIPTION>
{job_description}
</JOB_DESCRIPTION>

<MASTER_RESUME>
{master_resume}
</MASTER_RESUME>

Respond ONLY with valid JSON matching this schema:
{{
  "cover_letter": "The full text of the cover letter in Markdown",
  "warnings": ["Any missing requirements you couldn't address"]
}}
"""
        import asyncio
        response = asyncio.run(
            self._client.generate(
                prompt,
                model=model_id,
                format="json",
                temperature=0.4,
                system="You are an elite executive career coach and copywriter. You write compelling, modern cover letters that open with a high-impact hook demonstrating candidate-company fit, avoiding robotic cliches.",
            )
        )
        try:
            parsed_dict = AtsAnalyzer._parse_json(response.text)
            return CoverLetter.model_validate(parsed_dict)
        except Exception as e:
            logger.error(f"Failed to parse cover letter: {response.text}")
            raise AtsAnalysisError("Invalid cover letter response from model") from e

    def parse_master_resume(self, raw_text: str, model_id: str | None = None) -> ParsedResumeData:
        prompt = f"""You are an expert data extractor.
Extract the core details and implicit preferences from this raw resume text.

<RESUME>
{raw_text}
</RESUME>

Respond ONLY with valid JSON matching this schema:
{{
  "preferences": {{
    "Candidate Name": "E.g. Alex Rivera",
    "Target Role": "E.g. Senior Software Engineer",
    "Location": "E.g. Remote or specific city",
    "Min Years Exp": "E.g. 5"
  }},
  "structured_json": "A stringified JSON representing the candidate's core skills, experience, and contact info"
}}
"""
        import asyncio
        response = asyncio.run(
            self._client.generate(
                prompt,
                model=model_id,
                format="json",
                temperature=0.0,
                system="You are a structured CV data extraction engine. Extract preferences and core skills into clean structured JSON.",
            )
        )
        try:
            parsed_dict = AtsAnalyzer._parse_json(response.text)
            return ParsedResumeData.model_validate(parsed_dict)
        except Exception as e:
            logger.error(f"Failed to parse master resume: {response.text}")
            raise AtsAnalysisError("Invalid parse response from model") from e

    @staticmethod
    def _parse_analysis(response: str) -> AtsAnalysis:
        try:
            data = AtsAnalyzer._parse_json(response)
            if isinstance(data, dict):
                fav = data.get("favoring_points")
                if fav and isinstance(fav, list):
                    data["favoring_points"] = clean_favoring_points(fav)
                elif "summary" in data:
                    data["favoring_points"] = clean_favoring_points([data["summary"], *data.get("recommendations", [])])
            return AtsAnalysis.model_validate(data)
        except ValueError as error:
            raise AtsAnalysisError("The local model returned an invalid ATS analysis") from error

    @staticmethod
    def _parse_tailoring(response: str) -> TailoredResume:
        try:
            return TailoredResume.model_validate(AtsAnalyzer._parse_json(response))
        except ValueError as error:
            raise AtsAnalysisError("The local model returned an invalid tailored resume") from error

    @staticmethod
    def _parse_json(response: str) -> Any:
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            
        try:
            start_idx = cleaned.find("{")
            end_idx = cleaned.rfind("}")
            if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
                cleaned = cleaned[start_idx:end_idx+1]
        except Exception:
            pass
            
        try:
            return json.loads(cleaned)
        except (json.JSONDecodeError, ValueError) as error:
            # Fallback: attempt to strip trailing commas that LLMs sometimes hallucinate
            import re
            patched = re.sub(r',\s*([\]}])', r'\1', cleaned)
            # Strip invalid control characters inside the JSON block (excluding newlines)
            patched = re.sub(r'[\x00-\x09\x0b-\x1f\x7f-\x9f]', '', patched)
            try:
                return json.loads(patched)
            except Exception:
                logger.error(f"Failed to parse JSON. Raw output:\n{response}")
                raise AtsAnalysisError(f"The local model did not return valid structured JSON.\nRaw output:\n{response}") from error


class AtsPlugin:
    name = "ats"
    requires = ("ollama",)

    def __init__(self) -> None:
        self._context: PluginContext | None = None

    async def start(self, context: PluginContext) -> None:
        client = context.services.get(OLLAMA_CLIENT_SERVICE)
        if not isinstance(client, OllamaClient):
            raise TypeError("The Ollama service has an unexpected type")
        context.services.provide(ATS_ANALYZER_SERVICE, AtsAnalyzer(client))
        self._context = context

    async def stop(self) -> None:
        if self._context is not None:
            self._context.services.remove(ATS_ANALYZER_SERVICE)
            self._context = None


def create_plugin() -> AtsPlugin:
    return AtsPlugin()
