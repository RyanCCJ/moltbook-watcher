from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

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
        ollama_timeout_seconds: float = 180,
        ollama_client: httpx.Client | None = None,
    ) -> None:
        self._ollama_model = ollama_model
        self._ollama_chat_url = f"{ollama_base_url.rstrip('/')}/api/chat"
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
            "You are a professional translator.\n"
            "Translate the input into Traditional Chinese (zh-Hant, Taiwan usage).\n"
            "Rules:\n"
            "- Preserve all meaning and paragraph structure.\n"
            "- Preserve Markdown elements (headings, lists, tables, links, code blocks).\n"
            "- Preserve URLs, handles, and code text.\n"
            "- Return only translated text, no explanations.\n"
            f"Input:\n{raw_content}"
        )
        try:
            payload = self._chat_with_think_fallback(prompt=prompt, think=False)
            return self._extract_chat_content(payload)
        except Exception as error:  # pragma: no cover - fallback path
            logger.warning("ollama_translation_fallback", reason=str(error))
            self._ollama_enabled = False
            return f"ZH: {raw_content}"

    def _chat_with_think_fallback(self, *, prompt: str, think: bool) -> dict[str, Any]:
        request_payload: dict[str, Any] = {
            "model": self._ollama_model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "think": think,
        }

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
                if "</think>" in content:
                    content = content.split("</think>", 1)[1].strip()
                content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL | re.IGNORECASE).strip()
                if content:
                    return content
        raise ValueError("empty_translation")

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
