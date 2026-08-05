import pytest

from openclaw.plugins.ats import AtsAnalysisError, AtsAnalyzer
from openclaw.plugins.ollama import OllamaCompletion


class StubOllamaClient:
    def __init__(self, response: str) -> None:
        self.response = response

    async def generate(self, prompt: str, *, model: str | None = None) -> OllamaCompletion:
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
