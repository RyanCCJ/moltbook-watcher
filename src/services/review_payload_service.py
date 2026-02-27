from __future__ import annotations

from dataclasses import dataclass

import httpx

from src.services.logging_service import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class ReviewPayload:
    english_draft: str
    chinese_translation_full: str
    risk_tags: list[str]
    follow_up_rationale: str | None


class ReviewPayloadService:
    def __init__(
        self,
        *,
        ollama_base_url: str = "http://localhost:11434",
        ollama_model: str = "qwen3:4b",
        use_ollama: bool = True,
        ollama_timeout_seconds: float = 60,
        ollama_client: httpx.Client | None = None,
    ) -> None:
        self._ollama_model = ollama_model
        self._ollama_generate_url = f"{ollama_base_url.rstrip('/')}/api/generate"
        self._ollama_enabled = use_ollama
        self._ollama_client = ollama_client or httpx.Client(timeout=ollama_timeout_seconds)
        self._owns_client = ollama_client is None

    def build_payload(self, *, raw_content: str, risk_score: int, is_follow_up: bool = False) -> ReviewPayload:
        risk_tags: list[str] = []
        if risk_score >= 4:
            risk_tags.append("high-risk")
        elif risk_score >= 2:
            risk_tags.append("medium-risk")
        else:
            risk_tags.append("low-risk")

        follow_up_rationale = "Follow-up candidate based on novelty delta" if is_follow_up else None
        zh_translation = self._translate_to_chinese(raw_content)

        return ReviewPayload(
            english_draft=raw_content,
            chinese_translation_full=zh_translation,
            risk_tags=risk_tags,
            follow_up_rationale=follow_up_rationale,
        )

    def close(self) -> None:
        if self._owns_client:
            self._ollama_client.close()

    def _translate_to_chinese(self, raw_content: str) -> str:
        if not self._ollama_enabled:
            return f"ZH: {raw_content}"

        prompt = (
            "Translate the following text into Traditional Chinese. "
            "Keep meaning faithful and concise. Return only the translated text.\n"
            f"Text:\n{raw_content}"
        )
        try:
            response = self._ollama_client.post(
                self._ollama_generate_url,
                json={
                    "model": self._ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "think": False,
                },
            )
            response.raise_for_status()
            payload = response.json()
            translated = str(payload.get("response", "")).strip()
            if translated:
                return translated
            raise ValueError("empty_translation")
        except Exception as error:  # pragma: no cover - fallback path
            logger.warning("ollama_translation_fallback", reason=str(error))
            self._ollama_enabled = False
            return f"ZH: {raw_content}"
