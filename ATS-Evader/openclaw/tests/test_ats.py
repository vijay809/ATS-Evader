import pytest

from openclaw.plugins.ats import AtsAnalysisError, AtsAnalyzer
from openclaw.plugins.ollama import OllamaCompletion


class StubOllamaClient:
    def __init__(self, response: str) -> None:
        self.response = response

    async def generate(self, prompt: str, *, model: str | None = None, **_kwargs: object) -> OllamaCompletion:
        return OllamaCompletion(model=model or "test-model", text=self.response)


async def test_ats_analysis_parses_structured_local_model_output() -> None:
    client = StubOllamaClient(
        '{"match_score": 72, "matched_keywords": ["Python"], '
        '"missing_keywords": ["SQL"], "recommendations": ["Add SQL experience"], '
        '"summary": "Strong technical alignment."}'
    )
    analyzer = AtsAnalyzer(client)  # type: ignore[arg-type]

    result = await analyzer.analyze("Python developer", "Python and SQL developer")

    assert result.match_score == 72
    assert result.missing_keywords == ["SQL"]
    assert result.missing_core_skills == []
    assert result.unsupported_details == []
    assert result.formatting_risks == []


async def test_ats_analysis_parses_gap_and_flag_fields() -> None:
    client = StubOllamaClient(
        '{"match_score": 65, "matched_keywords": ["Python"], '
        '"missing_keywords": ["Kubernetes"], '
        '"missing_core_skills": ["Kubernetes", "Docker"], '
        '"unsupported_details": ["Requires 8+ years distributed systems"], '
        '"formatting_risks": ["Acronym K8s missing expansion"], '
        '"recommendations": ["Expand acronyms"], '
        '"summary": "Moderate alignment with critical infra gaps."}'
    )
    analyzer = AtsAnalyzer(client)  # type: ignore[arg-type]

    result = await analyzer.analyze("Python developer", "DevOps & Python developer")

    assert result.match_score == 65
    assert result.missing_core_skills == ["Kubernetes", "Docker"]
    assert result.unsupported_details == ["Requires 8+ years distributed systems"]
    assert result.formatting_risks == ["Acronym K8s missing expansion"]


async def test_ats_analysis_rejects_unstructured_model_output() -> None:
    analyzer = AtsAnalyzer(StubOllamaClient("Here is some advice"))  # type: ignore[arg-type]

    with pytest.raises(AtsAnalysisError, match="valid structured JSON"):
        await analyzer.analyze("Resume", "Job description")


async def test_resume_tailoring_preserves_structured_warnings() -> None:
    client = StubOllamaClient(
        '{"tailored_resume": "Experienced Python developer", '
        '"change_summary": ["Prioritized Python work"], '
        '"warnings": ["No SQL experience supplied"]}'
    )
    analyzer = AtsAnalyzer(client)  # type: ignore[arg-type]

    result = await analyzer.tailor("Python developer", "Python and SQL developer")

    assert result.tailored_resume == "Experienced Python developer"
    assert result.warnings == ["No SQL experience supplied"]


async def test_ats_analysis_retries_on_invalid_json() -> None:
    class RetryingStubOllamaClient:
        def __init__(self) -> None:
            self.calls = 0

        async def generate(self, prompt: str, *, model: str | None = None, **_kwargs: object) -> OllamaCompletion:
            self.calls += 1
            if self.calls == 1:
                return OllamaCompletion(model=model or "test-model", text="Invalid Response")
            return OllamaCompletion(
                model=model or "test-model",
                text='{"match_score": 50, "matched_keywords": [], "missing_keywords": [], "recommendations": [], "summary": "Valid now."}',
            )

    client = RetryingStubOllamaClient()
    analyzer = AtsAnalyzer(client)  # type: ignore[arg-type]

    result = await analyzer.analyze("Resume", "Job description")
    assert result.match_score == 50
    assert client.calls == 2


async def test_ats_analysis_fails_after_max_retries() -> None:
    class FailingStubOllamaClient:
        def __init__(self) -> None:
            self.calls = 0

        async def generate(self, prompt: str, *, model: str | None = None, **_kwargs: object) -> OllamaCompletion:
            self.calls += 1
            return OllamaCompletion(model=model or "test-model", text="Still Invalid")

    client = FailingStubOllamaClient()
    analyzer = AtsAnalyzer(client)  # type: ignore[arg-type]

    with pytest.raises(AtsAnalysisError):
        await analyzer.analyze("Resume", "Job description")
    
    assert client.calls == 3


def test_clean_favoring_points_filters_negatives_and_condenses() -> None:
    from openclaw.plugins.ats import clean_favoring_points

    raw = [
        "The candidate is a highly experienced Senior Software Engineer with strong proficiency in modern frontend and Python-based backend development, including demonstrable experience with Generative AI via LangChain. The seniority and functional domain (Enterprise Systems) align well. However, the resume presents critical gaps in the core technical requirements, specifically lacking proficiency in .NET/C# and hands-on experience with the required Azure cloud ecosystem and specific database technologies (SQL Server, Cosmos DB, Redis). The lack of C#/.NET experience is a major blocker for this role.",
        "The candidate is a strong functional fit (Enterprise, Seniority, AI/LLM concepts) but lacks the core required technology stack (.NET/C# and Azure).",
        "If the role is flexible, the candidate's Python/LangChain experience is highly relevant to the AI component.",
        "The candidate must explicitly detail experience with C#/.NET and Azure services to be considered a strong match for this specific JD.",
    ]

    points = clean_favoring_points(raw)

    # Must contain positive points
    assert any("modern frontend and Python-based backend development" in p for p in points)
    assert any("Generative AI via LangChain" in p for p in points)
    assert any("Enterprise Systems" in p for p in points)
    assert any("functional fit" in p for p in points)
    assert any("Python/LangChain experience is highly relevant" in p for p in points)

    # Must NOT contain any negative phrases or blocker caveats
    for p in points:
        assert "however" not in p.lower()
        assert "critical gaps" not in p.lower()
        assert "major blocker" not in p.lower()
        assert "lacks" not in p.lower()
        assert "must explicitly" not in p.lower()


def test_club_missing_skills_clusters_and_comma_separates() -> None:
    from openclaw.plugins.ats import club_missing_skills

    raw_skills = [
        ".NET",
        "C#",
        "ASP.NET Core",
        "Azure Cloud Services (Azure OpenAI, AKS, Azure Functions)",
        "SQL Server",
        "Cosmos DB",
        "Redis",
        "Docker",
        "Kubernetes",
    ]

    clubbed = club_missing_skills(raw_skills)
    assert len(clubbed) == 4
    assert ".NET, C#, ASP.NET Core" in clubbed
    assert "Azure Cloud Services (Azure OpenAI, AKS, Azure Functions)" in clubbed
    assert "SQL Server, Cosmos DB, Redis" in clubbed
    assert "Docker, Kubernetes" in clubbed


async def test_ats_analysis_coerces_string_recommendations_and_loose_fields() -> None:
    # Simulates the exact response observed from local Ollama where recommendations was a string
    client = StubOllamaClient(
        '{\n'
        '  "match_score": "75%",\n'
        '  "matched_keywords": ["Python", "React"],\n'
        '  "missing_keywords": "Cloud",\n'
        '  "recommendations": "Add cloud infrastructure experience.",\n'
        '  "summary": "Strong candidate."\n'
        '}'
    )
    analyzer = AtsAnalyzer(client)  # type: ignore[arg-type]

    result = await analyzer.analyze("Python developer", "Cloud developer")
    assert result.match_score == 75
    assert result.missing_keywords == ["Cloud"]
    assert result.recommendations == ["Add cloud infrastructure experience."]
    assert result.summary == "Strong candidate."


