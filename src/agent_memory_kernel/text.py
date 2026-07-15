"""Deterministic lexical helpers used by the v0.1 local fallback retriever."""

from __future__ import annotations

import re


def tokens(text: str) -> set[str]:
    lowered = text.lower()
    result = set(re.findall(r"[a-z0-9_.-]{2,}", lowered))
    for chunk in re.findall(r"[\u3400-\u9fff]+", lowered):
        if len(chunk) <= 4:
            result.add(chunk)
        result.update(chunk[index:index + 2] for index in range(max(1, len(chunk) - 1)))
    return {token for token in result if token}


def token_coverage(query_tokens: set[str], content: str) -> float:
    if not query_tokens:
        return 1.0
    return len(query_tokens & tokens(content)) / len(query_tokens)
