"""Local, structured ATS resume analysis capability."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from openclaw.plugins.manager import PluginContext
from openclaw.plugins.ollama import OLLAMA_CLIENT_SERVICE, OllamaClient

ATS_ANALYZER_SERVICE = "ats.analyzer"


class AtsAnalysis(BaseModel):
    match_score: int = Field(ge=0, le=100)
    matched_keywords: list[str]
    missing_keywords: list[str]
    recommendations: list[str]
    summary: str


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
        completion = await self._client.generate(prompt, model=model)
        return self._parse_analysis(completion.text)

    async def tailor(
        self,
        resume: str,
        job_description: str,
        *,
        model: str | None = None,
    ) -> TailoredResume:
        if not resume.strip() or not job_description.strip():
            raise ValueError("Both resume and job description are required")
        completion = await self._client.generate(self._build_tailoring_prompt(resume, job_description), model=model)
        return self._parse_tailoring(completion.text)

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
