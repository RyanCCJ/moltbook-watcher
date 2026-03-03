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
        ollama_timeout_seconds: float = 60,
        ollama_client: httpx.Client | None = None,
    ) -> None:
        self.risk_penalty_weight = risk_penalty_weight
        self.score_version = score_version
        self._ollama_model = ollama_model
        self._ollama_chat_url = f"{ollama_base_url.rstrip('/')}/api/chat"
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
            "Do not include markdown fences or additional explanation.\n"
            f"Likes={likes}, comments={comments}\n"
            f"Content:\n{content_text}"
        )
        response_format = {
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
        }

        try:
            payload = self._chat_with_think_fallback(
                prompt=prompt,
                think=True,
                response_format=response_format,
            )
            raw_response = self._extract_chat_content(payload)
            try:
                parsed = self._parse_json_object(raw_response)
            except ValueError:
                retry_prompt = (
                    "Return ONLY a valid compact JSON object with keys: novelty, depth, tension, "
                    "reflective_impact, engagement, risk.\n"
                    "No markdown, no extra words.\n"
                    "Range: novelty/depth/tension/reflective_impact/engagement 0..5, risk 0..5.\n"
                    f"Likes={likes}, comments={comments}\n"
                    f"Content:\n{content_text}"
                )
                retry_payload = self._chat_with_think_fallback(
                    prompt=retry_prompt,
                    think=True,
                    response_format="json",
                )
                retry_response_text = self._extract_chat_content(retry_payload)
                parsed = self._parse_json_object(retry_response_text)

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
            if isinstance(error, httpx.HTTPError):
                self._ollama_enabled = False
            return None

    def _chat_with_think_fallback(
        self,
        *,
        prompt: str,
        think: bool,
        response_format: Any | None = None,
    ) -> dict[str, Any]:
        request_payload: dict[str, Any] = {
            "model": self._ollama_model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "think": think,
        }
        if response_format is not None:
            request_payload["format"] = response_format

        response = self._ollama_client.post(self._ollama_chat_url, json=request_payload)
        if response.status_code < 400:
            return response.json()

        if not self._is_unknown_param_error(response, "think"):
            response.raise_for_status()

        compat_payload = dict(request_payload)
        compat_payload.pop("think", None)
        compat_payload["thinking"] = think

        compat_response = self._ollama_client.post(self._ollama_chat_url, json=compat_payload)
        compat_response.raise_for_status()
        return compat_response.json()

    @staticmethod
    def _extract_chat_content(payload: dict[str, Any]) -> str:
        message = payload.get("message")
        if isinstance(message, dict):
            content = str(message.get("content", "")).strip()
            if content:
                return content
        raise ValueError("empty_chat_content")

    @staticmethod
    def _is_unknown_param_error(response: httpx.Response, param_name: str) -> bool:
        body = response.text.lower()
        return (
            param_name.lower() in body
            and (
                "unknown" in body
                or "invalid" in body
                or "unmarshal" in body
                or "unexpected" in body
            )
        )

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
