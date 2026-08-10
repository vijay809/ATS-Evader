"""Local, structured ATS resume analysis capability."""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from openclaw.plugins.manager import PluginContext
from openclaw.plugins.ollama import OLLAMA_CLIENT_SERVICE, OllamaClient

logger = logging.getLogger(__name__)

ATS_ANALYZER_SERVICE = "ats.analyzer"


class AtsAnalysis(BaseModel):
    match_score: int = Field(ge=0, le=100)
    matched_keywords: list[str]
    missing_keywords: list[str]
    recommendations: list[str]
    summary: str


class ParsedResumeData(BaseModel):
    preferences: dict[str, str]
    structured_json: str


class TailoredResume(BaseModel):
    tailored_resume: str
    change_summary: list[str]
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
            completion = await self._client.generate(prompt, model=model)
            try:
                return self._parse_analysis(completion.text)
            except AtsAnalysisError as error:
                if attempt == 2:
                    raise
                logger.warning(f"Failed to parse ATS analysis on attempt {attempt + 1}: {error}")
                prompt += f"\n\nYour previous response was invalid: {error}. Please fix it and return ONLY valid JSON matching the exact schema."
        raise AtsAnalysisError("Failed to generate valid ATS analysis after retries")

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
            completion = await self._client.generate(prompt, model=model)
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
        return f"""You are an ATS resume analyst. Compare the resume against the job description.
Return only valid JSON with this exact schema:
{{
  "match_score": integer from 0 to 100,
  "matched_keywords": [string],
  "missing_keywords": [string],
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
        return f"""You are a careful resume editor. Tailor the supplied resume for the job description.
Never invent achievements, employers, titles, dates, degrees, certifications, skills, tools, or metrics.
Keep every factual claim grounded in the original resume. If a requirement is unsupported, place it in warnings.
Return only valid JSON with this exact schema:
{{
  "tailored_resume": string,
  "change_summary": [string],
  "warnings": [string]
}}

Resume:
---
{resume}
---

Job description:
---
{job_description}
---"""

    def tailor_resume(self, master_resume: str, job_description: str, model_id: str = "gemma4:12b") -> TailoredResume:
        prompt = f"""You are an expert ATS optimizer and resume writer.
I will provide a master resume and a job description.
Tailor the resume to match the job description perfectly while remaining truthful.

<JOB_DESCRIPTION>
{job_description}
</JOB_DESCRIPTION>

<MASTER_RESUME>
{master_resume}
</MASTER_RESUME>

Respond ONLY with valid JSON matching this schema:
{{
  "tailored_resume": "The full text of the tailored resume",
  "change_summary": ["Changed X to Y", "Added emphasis on Z"],
  "warnings": ["Could not match requirement A"]
}}
"""
        import asyncio
        response = asyncio.run(self._client.generate(prompt, model=model_id))
        try:
            return TailoredResume.model_validate_json(response.text)
        except Exception as e:
            logger.error(f"Failed to parse tailored resume: {response.text}")
            raise AtsAnalysisError("Invalid tailor response from model") from e

    def parse_master_resume(self, raw_text: str, model_id: str = "gemma4:12b") -> ParsedResumeData:
        prompt = f"""You are an expert data extractor.
Extract the core details and implicit preferences from this raw resume text.

<RESUME>
{raw_text}
</RESUME>

Respond ONLY with valid JSON matching this schema:
{{
  "preferences": {{
    "Target Role": "E.g. Senior Software Engineer",
    "Location": "E.g. Remote or specific city",
    "Min Years Exp": "E.g. 5"
  }},
  "structured_json": "A stringified JSON representing the candidate's core skills, experience, and contact info"
}}
"""
        import asyncio
        response = asyncio.run(self._client.generate(prompt, model=model_id))
        try:
            return ParsedResumeData.model_validate_json(response.text)
        except Exception as e:
            logger.error(f"Failed to parse master resume: {response.text}")
            raise AtsAnalysisError("Invalid parse response from model") from e

    @staticmethod
    def _parse_analysis(response: str) -> AtsAnalysis:
        try:
            return AtsAnalysis.model_validate(AtsAnalyzer._parse_json(response))
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
            return json.loads(cleaned)
        except (json.JSONDecodeError, ValueError) as error:
            raise AtsAnalysisError("The local model did not return valid structured JSON") from error


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
