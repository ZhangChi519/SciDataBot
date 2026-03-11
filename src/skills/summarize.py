"""Summarize skill for condensing long content."""
from typing import Any, Dict, Optional

from src.tools.base import Tool, ToolResult, ToolCategory


class SummarizeSkill(Tool):
    """Skill for summarizing text content."""

    name = "summarize"
    description = "Summarize long text content"
    category = ToolCategory.DATA_PROCESSING

    def __init__(self):
        """Initialize summarize skill."""
        pass

    async def execute(self, operation: str, **kwargs) -> ToolResult:
        """Execute summarize operation."""
        try:
            if operation == "summarize":
                return await self._summarize(
                    kwargs.get("content"),
                    kwargs.get("max_length", 200),
                    kwargs.get("style", "brief"),
                )
            elif operation == "extract_key_points":
                return await self._extract_key_points(kwargs.get("content"))
            else:
                return ToolResult(success=False, error=f"Unknown operation: {operation}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _summarize(
        self,
        content: str,
        max_length: int,
        style: str,
    ) -> ToolResult:
        """Summarize content."""
        if not content:
            return ToolResult(success=False, error="Content is required")

        # Simple extractive summarization
        sentences = content.replace("!", ".").replace("?", ".").split(".")

        if len(sentences) <= 3:
            return ToolResult(success=True, data={"summary": content[:max_length]})

        # Score sentences by length and position
        scored = []
        for i, sentence in enumerate(sentences):
            if sentence.strip():
                score = len(sentence) * (1.0 / (i + 1))  # Prefer earlier sentences
                scored.append((score, sentence.strip()))

        scored.sort(reverse=True)

        # Build summary
        summary = []
        current_length = 0

        for score, sentence in scored:
            if current_length + len(sentence) > max_length:
                break
            summary.append(sentence)
            current_length += len(sentence)

        return ToolResult(
            success=True,
            data={
                "summary": ". ".join(summary) + ".",
                "original_length": len(content),
                "summary_length": current_length,
            },
        )

    async def _extract_key_points(self, content: str) -> ToolResult:
        """Extract key points from content."""
        if not content:
            return ToolResult(success=False, error="Content is required")

        # Simple key point extraction based on sentence length and content
        sentences = content.replace("!", ".").replace("?", ".").split(".")

        key_points = []

        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 20:  # Skip very short sentences
                continue

            # Look for sentences with important words
            important_indicators = [
                "important", "key", "main", "primary",
                "significant", "essential", "critical",
                "first", "second", "finally", "conclusion",
            ]

            sentence_lower = sentence.lower()
            if any(indicator in sentence_lower for indicator in important_indicators):
                key_points.append(sentence)

        # If not enough key points, take the longest sentences
        if len(key_points) < 3:
            scored = [(len(s), s) for s in sentences if len(s.strip()) > 30]
            scored.sort(reverse=True)
            key_points = [s for _, s in scored[:5]]

        return ToolResult(
            success=True,
            data={"key_points": key_points, "count": len(key_points)},
        )
