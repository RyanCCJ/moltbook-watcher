from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import httpx

from src.services.logging_service import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class ScoreVector:
    novelty: float
    depth: float
    tension: float
    reflective_impact: float
    engagement: float
    risk: int


@dataclass(slots=True)
class ScoreResult:
    novelty: float
    depth: float
    tension: float
    reflective_impact: float
    engagement: float
    risk: int
    content_score: float
    final_score: float
    score_version: str


class ScoringService:
    def __init__(
        self,
        risk_penalty_weight: float = 0.2,
        score_version: str = "v1",
        *,
        ollama_base_url: str = "http://localhost:11434",
        ollama_model: str = "qwen3:4b",
        use_ollama: bool = True,
        ollama_timeout_seconds: float = 10,
        ollama_client: httpx.Client | None = None,
    ) -> None:
        self.risk_penalty_weight = risk_penalty_weight
        self.score_version = score_version
        self._ollama_model = ollama_model
        self._ollama_generate_url = f"{ollama_base_url.rstrip('/')}/api/generate"
        self._ollama_enabled = use_ollama
        self._ollama_client = ollama_client or httpx.Client(timeout=ollama_timeout_seconds)
        self._owns_client = ollama_client is None

    def compute_scores(self, vector: ScoreVector) -> ScoreResult:
        content_score = round(
            (vector.novelty + vector.depth + vector.tension + vector.reflective_impact + vector.engagement)
            / 5,
            2,
        )
        final_score = round(content_score - (vector.risk * self.risk_penalty_weight), 2)
        final_score = max(0.0, min(5.0, final_score))

        return ScoreResult(
            novelty=vector.novelty,
            depth=vector.depth,
            tension=vector.tension,
            reflective_impact=vector.reflective_impact,
            engagement=vector.engagement,
            risk=vector.risk,
            content_score=content_score,
            final_score=final_score,
            score_version=self.score_version,
        )

    def score_candidate(self, content_text: str, engagement_summary: dict | None = None) -> ScoreResult:
        ollama_vector = self._score_with_ollama(content_text, engagement_summary or {})
        if ollama_vector is not None:
            return self.compute_scores(ollama_vector)

        return self.compute_scores(self._score_with_heuristic(content_text, engagement_summary))

    def close(self) -> None:
        if self._owns_client:
            self._ollama_client.close()

    def _score_with_heuristic(self, content_text: str, engagement_summary: dict | None = None) -> ScoreVector:
        likes = int((engagement_summary or {}).get("likes", 0))
        text_len = len(content_text.strip())

        novelty = min(5.0, round(2.0 + text_len / 120, 2))
        depth = min(5.0, round(1.5 + text_len / 150, 2))
        tension = min(5.0, round(1.0 + ("?" in content_text) * 1.5 + ("!" in content_text) * 0.5, 2))
        reflective_impact = min(5.0, round(1.5 + text_len / 180, 2))
        engagement = min(5.0, round(1.0 + likes / 10, 2))
        risk = 1 if "unsafe" not in content_text.lower() else 4

        return ScoreVector(
            novelty=novelty,
            depth=depth,
            tension=tension,
            reflective_impact=reflective_impact,
            engagement=engagement,
            risk=risk,
        )

    def _score_with_ollama(self, content_text: str, engagement_summary: dict[str, Any]) -> ScoreVector | None:
        if not self._ollama_enabled:
            return None

        likes = int(engagement_summary.get("likes", 0))
        comments = int(engagement_summary.get("comments", 0))

        prompt = (
            "Return only compact JSON with keys novelty, depth, tension, reflective_impact, engagement, risk. "
            "Scores must be numeric in range: novelty/depth/tension/reflective_impact/engagement 0..5, risk 0..5.\n"
            f"Likes={likes}, comments={comments}\n"
            f"Content:\n{content_text}"
        )

        try:
            response = self._ollama_client.post(
                self._ollama_generate_url,
                json={
                    "model": self._ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "format": {
                        "type": "object",
                        "properties": {
                            "novelty": {"type": "number"},
                            "depth": {"type": "number"},
                            "tension": {"type": "number"},
                            "reflective_impact": {"type": "number"},
                            "engagement": {"type": "number"},
                            "risk": {"type": "number"},
                        },
                        "required": [
                            "novelty",
                            "depth",
                            "tension",
                            "reflective_impact",
                            "engagement",
                            "risk",
                        ],
                    },
                    "think": False,
                },
            )
            response.raise_for_status()
            payload = response.json()
            raw_response = payload.get("response", "")
            parsed = self._parse_json_object(raw_response)

            return ScoreVector(
                novelty=self._coerce_float(parsed, "novelty"),
                depth=self._coerce_float(parsed, "depth"),
                tension=self._coerce_float(parsed, "tension"),
                reflective_impact=self._coerce_float(parsed, "reflective_impact"),
                engagement=self._coerce_float(parsed, "engagement"),
                risk=self._coerce_int(parsed, "risk"),
            )
        except Exception as error:  # pragma: no cover - fallback path
            logger.warning("ollama_scoring_fallback", reason=str(error))
            self._ollama_enabled = False
            return None

    @staticmethod
    def _parse_json_object(raw_response: str) -> dict[str, Any]:
        raw_response = raw_response.strip()
        if raw_response:
            try:
                parsed = json.loads(raw_response)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                match = re.search(r"\{.*\}", raw_response, flags=re.DOTALL)
                if match is not None:
                    parsed = json.loads(match.group(0))
                    if isinstance(parsed, dict):
                        return parsed
        raise ValueError("invalid_ollama_json")

    @staticmethod
    def _coerce_float(payload: dict[str, Any], key: str) -> float:
        value = float(payload[key])
        return max(0.0, min(5.0, round(value, 2)))

    @staticmethod
    def _coerce_int(payload: dict[str, Any], key: str) -> int:
        value = int(round(float(payload[key])))
        return max(0, min(5, value))
