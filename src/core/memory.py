"""Memory system for persistent agent memory."""

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from src.providers.base import LLMProvider


def _ensure_dir(path: Path) -> Path:
    """Ensure directory exists."""
    path.mkdir(parents=True, exist_ok=True)
    return path


_SAVE_MEMORY_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Save the memory consolidation result to persistent storage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "history_entry": {
                        "type": "string",
                        "description": "A paragraph (2-5 sentences) summarizing key events/decisions/topics. "
                        "Start with [YYYY-MM-DD HH:MM]. Include detail useful for grep search.",
                    },
                    "memory_update": {
                        "type": "string",
                        "description": "Full updated long-term memory as markdown. Include all existing "
                        "facts plus new ones. Return unchanged if nothing new.",
                    },
                },
                "required": ["history_entry", "memory_update"],
            },
        },
    }
]


class MemoryStore:
    """双层记忆系统：MEMORY.md（长期事实）+ HISTORY.md（可搜索日志）"""

    def __init__(self, channel_dir: Path):
        """初始化记忆存储
        
        Args:
            channel_dir: channel 目录路径 (e.g., ~/.scidatabot/console)
                        会在此目录下创建 memory/ 子目录
        """
        self.memory_dir = _ensure_dir(channel_dir / "memory")
        self.memory_file = self.memory_dir / "MEMORY.md"
        self.history_file = self.memory_dir / "HISTORY.md"

    def read_long_term(self) -> str:
        """读取长期记忆"""
        if self.memory_file.exists():
            return self.memory_file.read_text(encoding="utf-8")
        return ""

    def write_long_term(self, content: str) -> None:
        """写入长期记忆"""
        self.memory_file.write_text(content, encoding="utf-8")

    def append_history(self, entry: str) -> None:
        """追加历史记录"""
        with open(self.history_file, "a", encoding="utf-8") as f:
            f.write(entry.rstrip() + "\n\n")

    def get_memory_context(self) -> str:
        """获取记忆上下文"""
        long_term = self.read_long_term()
        return f"## Long-term Memory\n{long_term}" if long_term else ""

    async def consolidate(
        self,
        session,
        provider: "LLMProvider",
        model: str,
        *,
        archive_all: bool = False,
        memory_window: int = 50,
    ) -> bool:
        """将旧消息整合到 MEMORY.md + HISTORY.md

        Args:
            session: Session 对象，需包含 messages, last_consolidated 属性
            provider: LLM Provider
            model: 模型名称
            archive_all: 是否归档所有消息
            memory_window: 记忆窗口大小

        Returns:
            整合成功返回 True，失败返回 False
        """
        if archive_all:
            old_messages = session.messages
            keep_count = 0
            logger.info("Memory consolidation (archive_all): {} messages", len(session.messages))
        else:
            keep_count = memory_window // 2
            if len(session.messages) <= keep_count:
                return True
            if len(session.messages) - session.last_consolidated <= 0:
                return True
            old_messages = session.messages[session.last_consolidated:-keep_count]
            if not old_messages:
                return True
            logger.info("Memory consolidation: {} to consolidate, {} keep", len(old_messages), keep_count)

        lines = []
        for m in old_messages:
            if not m.get("content"):
                continue
            tools = f" [tools: {', '.join(m.get('tools_used', []))}]" if m.get("tools_used") else ""
            timestamp = m.get("timestamp", "?")[:16]
            role = m.get("role", "?").upper()
            content = m.get("content", "")
            lines.append(f"[{timestamp}] {role}{tools}: {content}")

        current_memory = self.read_long_term()
        prompt = f"""Process this conversation and call the save_memory tool with your consolidation.

## Current Long-term Memory
{current_memory or "(empty)"}

## Conversation to Process
{chr(10).join(lines)}"""

        try:
            response = await provider.chat(
                messages=[
                    {"role": "system", "content": "You are a memory consolidation agent. Call the save_memory tool with your consolidation of the conversation."},
                    {"role": "user", "content": prompt},
                ],
                tools=_SAVE_MEMORY_TOOL,
                model=model,
            )

            if not response.has_tool_calls:
                logger.warning("Memory consolidation: LLM did not call save_memory, skipping")
                return False

            args = response.tool_calls[0].arguments
            if isinstance(args, str):
                args = json.loads(args)
            if not isinstance(args, dict):
                logger.warning("Memory consolidation: unexpected arguments type {}", type(args).__name__)
                return False

            if entry := args.get("history_entry"):
                if not isinstance(entry, str):
                    entry = json.dumps(entry, ensure_ascii=False)
                self.append_history(entry)
            if update := args.get("memory_update"):
                if not isinstance(update, str):
                    update = json.dumps(update, ensure_ascii=False)
                if update != current_memory:
                    self.write_long_term(update)

            session.last_consolidated = 0 if archive_all else len(session.messages) - keep_count
            logger.info("Memory consolidation done: {} messages, last_consolidated={}", len(session.messages), session.last_consolidated)
            return True
        except Exception:
            logger.exception("Memory consolidation failed")
            return False
