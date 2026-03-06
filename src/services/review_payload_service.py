from __future__ import annotations

import asyncio
import json
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

    async def build_payload(
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
            translated_content, translated_comments = await self._translate_batch(
                raw_content,
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
            threads_draft = await self._generate_threads_draft(
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

    async def _translate(self, content: str, target_language: str) -> str:
        if not content.strip():
            return ""
        if not self._ollama_enabled:
            return ""

        prompt = (
            "You are a professional, highly accurate translation engine.\n"
            f"Target language: {self._describe_language(target_language)} ({target_language}).\n"
            "Task:\n"
            f"- Translate the full input into {target_language} naturally and fluently.\n"
            "Rules:\n"
            "- CRITICAL: Do NOT copy or output the text in its original language. You MUST translate every sentence.\n"
            "- Preserve all meaning and paragraph structure.\n"
            "- Preserve Markdown elements (headings, lists, tables, links, code blocks).\n"
            "- Keep URLs, handles, product names, and code tokens unchanged.\n"
            "- Return only translated text, no explanations, no notes.\n"
            f"Input:\n{content}\n"
            f"Final reminder: The output MUST be entirely in {target_language}.\n"
        )
        try:
            payload = await self._chat_with_think_fallback(prompt=prompt, think=False)
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

    async def _generate_threads_draft(
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
            "- Spark curiosity and drive traffic to the original Moltbook post.\n"
            "- Deliver immediate value (a sharp insight or key takeaway), then leave them wanting the full context.\n"
            "Rules:\n"
            "- Use a natural, authentic conversational tone (like talking to a smart peer).\n"
            "- MUST start with the hook wrapped in solid brackets like 【 Your Intriguing Hook 】. This hook MUST be strictly one, short sentence.\n"
            "- No bullet points, numbered lists, or Markdown syntax.\n"
            "- Do not include any URLs.\n"
            "- Use emojis sparingly (max 1 or 2 total).\n"
            "- STRICTLY NO forced, generic reflections (e.g., 'This makes us ponder the future'). Keep it grounded and substantive.\n"
            "Length:\n"
            "- Concise but substantive: 3 to 4 short paragraphs. Provide enough depth to deliver real value while respecting attention spans.\n"
            "Content strategy:\n"
            "- Paragraph 1: The Hook. Make it curious or relatable. Do not use cheap, sensationalist clickbait.\n"
            "- Paragraph 2 & 3: The Meat (Core Insights). Digest the most valuable signals, arguments, or data from the post and comments. Summarize the 'why' and the 'how' so the reader learns something useful immediately.\n"
            "- Paragraph 4: The Kicker. End with a specific, provocative question to spark debate, or a brief cliffhanger indicating the full post has deeper context.\n"
            f"Post content:\n{raw_content}\n\n"
            f"{comments_section}\n\n"
            "Return only the final post text."
        )

        try:
            payload = await self._chat_with_think_fallback(prompt=prompt, think=True)
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

    async def _translate_comments(
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
                    "content_text": await self._translate(comment.content_text, target_language),
                    "upvotes": comment.upvotes,
                }
            )
        return translated

    async def _translate_batch(
        self,
        content: str,
        comments: list[MoltbookComment],
        *,
        target_language: str,
    ) -> tuple[str, list[dict[str, Any]]]:
        if not self._ollama_enabled:
            return "", await self._translate_comments(comments, target_language=target_language)

        input_payload: dict[str, str] = {}
        if content.strip():
            input_payload["content"] = content

        comment_keys: list[str | None] = []
        for index, comment in enumerate(comments, start=1):
            if comment.content_text.strip():
                key = f"comment_{index}"
                input_payload[key] = comment.content_text
                comment_keys.append(key)
            else:
                comment_keys.append(None)

        if not input_payload:
            translated_comments = [
                {
                    "author_handle": comment.author_handle,
                    "content_text": "",
                    "upvotes": comment.upvotes,
                }
                for comment in comments
            ]
            return "", translated_comments

        response_format = {
            "type": "object",
            "properties": {key: {"type": "string"} for key in input_payload},
            "required": list(input_payload.keys()),
        }

        prompt = (
            "You are a professional, highly accurate translation engine.\n"
            f"Target language: {self._describe_language(target_language)} ({target_language}).\n"
            f"Task: Translate every string value in the provided JSON object into {target_language}.\n"
            "Rules:\n"
            "- CRITICAL: Do NOT copy the original text. You MUST translate every single value into the target language.\n"
            "- Keep the JSON structure and keys exactly unchanged.\n"
            "- Preserve original meaning, style, and any Markdown elements within the text.\n"
            "- Keep URLs, handles, product names, and code tokens unchanged.\n"
            "- Return only valid JSON with the exact same keys.\n"
            f"Input JSON:\n{json.dumps(input_payload, ensure_ascii=False)}"
        )

        try:
            payload = await self._chat_with_think_fallback(
                prompt=prompt,
                think=False,
                response_format=response_format,
            )
            raw_response = self._extract_chat_content(payload)
            parsed = self._parse_json_object(raw_response)
            missing_keys = [key for key in input_payload if key not in parsed]
            if missing_keys:
                raise ValueError(f"missing_keys: {','.join(missing_keys)}")

            translated_content = str(parsed.get("content", "")).strip()
            translated_comments: list[dict[str, Any]] = []
            for index, comment in enumerate(comments):
                key = comment_keys[index]
                translated_text = str(parsed[key]).strip() if key else ""
                translated_comments.append(
                    {
                        "author_handle": comment.author_handle,
                        "content_text": translated_text,
                        "upvotes": comment.upvotes,
                    }
                )
            return translated_content, translated_comments
        except ValueError as error:
            logger.warning("ollama_batch_translation_parse_failed", reason=str(error))
        except Exception as error:  # pragma: no cover - network failure path
            logger.warning("ollama_batch_translation_failed", reason=str(error))
            if isinstance(error, httpx.HTTPError):
                self._ollama_enabled = False

        translated_content = await self._translate(content, target_language)
        translated_comments = await self._translate_comments(comments, target_language=target_language)
        return translated_content, translated_comments

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

    async def _chat_with_think_fallback(
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

        response = await asyncio.to_thread(lambda: self._ollama_client.post(self._ollama_chat_url, json=request_payload))
        if response.status_code < 400:
            return response.json()

        if not self._is_unknown_param_error(response, "think"):
            response.raise_for_status()

        compat_payload = dict(request_payload)
        if think:
            compat_payload["think"] = False
        else:
            compat_payload.pop("think", None)

        compat_response = await asyncio.to_thread(
            lambda: self._ollama_client.post(self._ollama_chat_url, json=compat_payload)
        )
        compat_response.raise_for_status()
        return compat_response.json()

    @staticmethod
    def _parse_json_object(raw_response: str) -> dict[str, Any]:
        stripped = raw_response.strip()
        if stripped:
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
                if match is not None:
                    parsed = json.loads(match.group(0))
                    if isinstance(parsed, dict):
                        return parsed
        raise ValueError("invalid_ollama_json")

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
