from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Any

import httpx

from src.services.logging_service import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from src.integrations.moltbook_api_client import MoltbookComment


@dataclass(slots=True)
class ReviewPayload:
    english_draft: str
    chinese_translation_full: str
    risk_tags: list[str]
    follow_up_rationale: str | None
    top_comments_snapshot: list[dict[str, Any]]
    top_comments_translated: list[dict[str, Any]]
    threads_draft: str


class ReviewPayloadService:
    def __init__(
        self,
        *,
        ollama_base_url: str = "http://localhost:11434",
        ollama_model: str = "qwen3:4b",
        use_ollama: bool = True,
        ollama_timeout_seconds: float = 180,
        ollama_client: httpx.Client | None = None,
        translation_language: str = "",
        threads_language: str = "en",
        threads_draft_min_score: float = 3.5,
    ) -> None:
        self._ollama_model = ollama_model
        self._ollama_chat_url = f"{ollama_base_url.rstrip('/')}/api/chat"
        self._ollama_enabled = use_ollama
        self._ollama_client = ollama_client or httpx.Client(timeout=ollama_timeout_seconds)
        self._owns_client = ollama_client is None
        self._translation_language = translation_language.strip()
        self._threads_language = threads_language.strip() or "en"
        self._threads_draft_min_score = threads_draft_min_score

    def build_payload(
        self,
        *,
        raw_content: str,
        risk_score: int,
        is_follow_up: bool = False,
        top_comments: list[MoltbookComment] | None = None,
        final_score: float | None = None,
        source_url: str = "",
    ) -> ReviewPayload:
        risk_tags: list[str] = []
        if risk_score >= 4:
            risk_tags.append("high-risk")
        elif risk_score >= 2:
            risk_tags.append("medium-risk")
        else:
            risk_tags.append("low-risk")

        follow_up_rationale = "Follow-up candidate based on novelty delta" if is_follow_up else None
        normalized_comments = top_comments or []
        comments_snapshot = self._serialize_comments(normalized_comments)

        if self._translation_language:
            translated_content = self._translate(raw_content, self._translation_language)
            translated_comments = self._translate_comments(
                normalized_comments,
                target_language=self._translation_language,
            )
        else:
            translated_content = ""
            translated_comments = []

        threads_draft = ""
        if (
            final_score is not None
            and final_score >= self._threads_draft_min_score
            and source_url.strip()
        ):
            threads_draft = self._generate_threads_draft(
                raw_content=raw_content,
                top_comments=normalized_comments,
                final_score=final_score,
                source_url=source_url,
            )

        return ReviewPayload(
            english_draft=raw_content,
            chinese_translation_full=translated_content,
            risk_tags=risk_tags,
            follow_up_rationale=follow_up_rationale,
            top_comments_snapshot=comments_snapshot,
            top_comments_translated=translated_comments,
            threads_draft=threads_draft,
        )

    def close(self) -> None:
        if self._owns_client:
            self._ollama_client.close()

    def _translate(self, content: str, target_language: str) -> str:
        if not content.strip():
            return ""
        if not self._ollama_enabled:
            return ""

        prompt = (
            "You are a professional translator.\n"
            f"Target language: {self._describe_language(target_language)} ({target_language}).\n"
            "Task:\n"
            "- Translate the full input into the target language naturally and faithfully.\n"
            "Rules:\n"
            "- Translate all sentences; do not leave full sentences in the source language.\n"
            "- Preserve all meaning and paragraph structure.\n"
            "- Preserve Markdown elements (headings, lists, tables, links, code blocks).\n"
            "- Keep URLs, handles, product names, and code tokens unchanged.\n"
            "- Return only translated text, no explanations, no notes.\n"
            f"Input:\n{content}\n"
            "Final reminder: The output MUST be entirely in the TARGET LANGUAGE.\n"
        )
        try:
            payload = self._chat_with_think_fallback(prompt=prompt, think=False)
            return self._extract_chat_content(payload)
        except Exception as error:  # pragma: no cover - fallback path
            logger.warning(
                "ollama_translation_fallback",
                target_language=target_language,
                reason=str(error),
            )
            if isinstance(error, httpx.HTTPError):
                self._ollama_enabled = False
            return ""

    def _generate_threads_draft(
        self,
        raw_content: str,
        top_comments: list[MoltbookComment],
        final_score: float,
        source_url: str,
    ) -> str:
        if not self._ollama_enabled:
            return ""

        _ = final_score
        comments_section = self._format_comments_for_prompt(top_comments)
        prompt = (
            "You are sharing a Moltbook post on Threads to attract clicks, likes, and discussion.\n"
            f"Write in {self._describe_language(self._threads_language)}.\n"
            "Goal:\n"
            "- Make people want to open the original Moltbook post.\n"
            "- Use a concise sharing/commentary angle, not a dry summary.\n"
            "Rules:\n"
            "- Use a natural conversational tone.\n"
            "- No bullet points or numbered lists.\n"
            "- No markdown syntax (headings, bold, links, code fences).\n"
            "- Do not include any URLs.\n"
            "- Avoid excessive emoji (max 2).\n"
            "- Do not invent facts beyond the source content/comments.\n"
            "Length:\n"
            "- 3 to 5 short paragraphs.\n"
            "Content strategy:\n"
            "- Start with a sharp hook in the first sentence.\n"
            "- If topic is thought-provoking/controversial, briefly comment on why it is interesting and potential human impact.\n"
            "- If article is high-signal/information-dense, make the key takeaway obvious in one sentence.\n"
            "- End with a simple call-to-action question to invite replies/likes.\n"
            f"Post content:\n{raw_content}\n\n"
            f"{comments_section}\n\n"
            "Return only the final post text."
        )

        try:
            payload = self._chat_with_think_fallback(prompt=prompt, think=True)
            generated = self._extract_chat_content(payload)
            generated = self._strip_urls(generated).strip()
            if not generated:
                return ""
            if self._is_near_copy_of_source(generated, raw_content):
                logger.warning("threads_draft_too_similar_to_source")
                return ""
            return f"{generated}\n\n{source_url}"
        except Exception as error:  # pragma: no cover - fallback path
            logger.warning("threads_draft_generation_failed", reason=str(error))
            if isinstance(error, httpx.HTTPError):
                self._ollama_enabled = False
            return ""

    def _translate_comments(
        self,
        comments: list[MoltbookComment],
        *,
        target_language: str,
    ) -> list[dict[str, Any]]:
        translated: list[dict[str, Any]] = []
        for comment in comments:
            translated.append(
                {
                    "author_handle": comment.author_handle,
                    "content_text": self._translate(comment.content_text, target_language),
                    "upvotes": comment.upvotes,
                }
            )
        return translated

    @staticmethod
    def _serialize_comments(comments: list[MoltbookComment]) -> list[dict[str, Any]]:
        return [
            {
                "author_handle": comment.author_handle,
                "content_text": comment.content_text,
                "upvotes": comment.upvotes,
            }
            for comment in comments
        ]

    @staticmethod
    def _format_comments_for_prompt(comments: list[MoltbookComment]) -> str:
        if not comments:
            return "Top comments:\n(none)"
        lines = []
        for index, comment in enumerate(comments[:5], start=1):
            author = comment.author_handle or "unknown"
            lines.append(f"{index}. @{author}: {comment.content_text}")
        return "Top comments:\n" + "\n".join(lines)

    @staticmethod
    def _strip_urls(text: str) -> str:
        return re.sub(r"https?://\S+", "", text)

    @staticmethod
    def _describe_language(language_code: str) -> str:
        normalized = language_code.strip().lower()
        names = {
            "zh": "Chinese",
            "zh-tw": "Traditional Chinese (Taiwan usage)",
            "zh-hant": "Traditional Chinese",
            "ja": "Japanese",
            "ko": "Korean",
            "en": "English",
            "pt-br": "Brazilian Portuguese",
        }
        return names.get(normalized, language_code)

    @staticmethod
    def _is_near_copy_of_source(generated: str, source: str, threshold: float = 0.9) -> bool:
        normalized_generated = re.sub(r"\s+", " ", generated).strip().lower()
        normalized_source = re.sub(r"\s+", " ", source).strip().lower()
        if not normalized_generated or not normalized_source:
            return False
        similarity = SequenceMatcher(None, normalized_generated, normalized_source).ratio()
        return similarity >= threshold

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
        if think:
            compat_payload["think"] = False
        else:
            compat_payload.pop("think", None)

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
        compat_error_patterns = (
            "unknown",
            "invalid",
            "unmarshal",
            "unexpected",
            "does not support thinking",
            "doesn't support thinking",
            "not support thinking",
        )
        return (
            param_name.lower() in body
            and any(pattern in body for pattern in compat_error_patterns)
        )
