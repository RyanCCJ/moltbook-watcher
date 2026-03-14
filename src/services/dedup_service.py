from __future__ import annotations

import hashlib
import re


class DedupService:
    def __init__(self, similarity_threshold: float = 0.8) -> None:
        self.similarity_threshold = similarity_threshold

    def build_fingerprint(self, text: str) -> str:
        tokens = self._normalize_tokens(text)
        joined = " ".join(sorted(set(tokens)))
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()

    def similarity(self, left: str, right: str) -> float:
        left_tokens = set(self._normalize_tokens(left))
        right_tokens = set(self._normalize_tokens(right))
        if not left_tokens and not right_tokens:
            return 1.0
        if not left_tokens or not right_tokens:
            return 0.0
        intersection = len(left_tokens & right_tokens)
        union = len(left_tokens | right_tokens)
        return intersection / union

    def should_filter(self, candidate_text: str, existing_texts: list[str]) -> bool:
        for existing in existing_texts:
            if self.similarity(candidate_text, existing) >= self.similarity_threshold:
                return True
        return False

    @staticmethod
    def _normalize_tokens(text: str) -> list[str]:
        raw_tokens = re.findall(r"[a-z0-9]+", text.lower())
        stopwords = {"a", "an", "the", "for", "by", "be", "should", "to", "of", "and"}

        normalized: list[str] = []
        for token in raw_tokens:
            if token in stopwords:
                continue
            normalized.append(_stem_token(token))
        return normalized


def _stem_token(token: str) -> str:
    if token.endswith("ied") and len(token) > 4:
        return f"{token[:-3]}y"
    if token.endswith("ed") and len(token) > 4:
        base = token[:-2]
        if not base.endswith("e"):
            base += "e"
        return base
    if token.endswith("ing") and len(token) > 5:
        return token[:-3]
    if token.endswith("s") and len(token) > 3:
        return token[:-1]
    return token
