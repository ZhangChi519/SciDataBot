"""Memory system for persistent agent memory - 借鉴NanoBot"""
import json
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from scidatabot.providers.base import LLMProvider
    from scidatabot.session import Session


class MemoryStore:
    """Two-layer memory: MEMORY.md (long-term facts) + HISTORY.md (grep-searchable log)."""

    def __init__(self, workspace: Path):
        self.memory_dir = workspace / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.memory_file = self.memory_dir / "MEMORY.md"
        self.history_file = self.memory_dir / "HISTORY.md"

    def read_long_term(self) -> str:
        """Read long-term memory."""
        if self.memory_file.exists():
            return self.memory_file.read_text(encoding="utf-8")
        return ""

    def write_long_term(self, content: str) -> None:
        """Write long-term memory."""
        self.memory_file.write_text(content, encoding="utf-8")

    def append_history(self, entry: str) -> None:
        """Append to history file."""
        with open(self.history_file, "a", encoding="utf-8") as f:
            f.write(entry.rstrip() + "\n\n")

    def get_memory_context(self) -> str:
        """Get memory context for prompts."""
        long_term = self.read_long_term()
        return f"## Long-term Memory\n{long_term}" if long_term else ""

    async def consolidate(
        self,
        session: "Session",
        provider: "LLMProvider",
        model: str,
        memory_window: int = 50,
    ) -> bool:
        """Consolidate old messages into MEMORY.md + HISTORY.md via LLM tool call."""
        keep_count = memory_window // 2
        
        if len(session.messages) <= keep_count:
            return True
            
        if session.get_unconsolidated_count() <= 0:
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
            timestamp = m.get("timestamp", "?")
            if isinstance(timestamp, float):
                from datetime import datetime
                timestamp = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")
            lines.append(f"[{timestamp}] {m['role'].upper()}{tools}: {m['content']}")

        current_memory = self.read_long_term()
        
        system_prompt = """You are a memory consolidation agent. Analyze the conversation and call save_memory to consolidate important information.

## Your task
1. Extract key facts, decisions, and topics from the conversation
2. Update long-term memory with important information
3. Create a history entry for searchability

Call save_memory tool with your consolidation."""

        user_prompt = f"""## Current Long-term Memory
{current_memory or "(empty)"}

## Conversation to Process
{chr(10).join(lines)}

Please consolidate this conversation."""

        try:
            response = await provider.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                tools=self._get_save_memory_tool(),
                model=model,
            )

            if not response.has_tool_calls:
                logger.warning("Memory consolidation: LLM did not call save_memory")
                return False

            args = response.tool_calls[0].arguments
            if isinstance(args, str):
                args = json.loads(args)
                
            if entry := args.get("history_entry"):
                if not isinstance(entry, str):
                    entry = json.dumps(entry, ensure_ascii=False)
                self.append_history(entry)
                
            if update := args.get("memory_update"):
                if not isinstance(update, str):
                    update = json.dumps(update, ensure_ascii=False)
                if update != current_memory:
                    self.write_long_term(update)

            session.last_consolidated = len(session.messages) - keep_count
            logger.info("Memory consolidation done")
            return True
            
        except Exception:
            logger.exception("Memory consolidation failed")
            return False

    def _get_save_memory_tool(self):
        """Return save_memory tool definition."""
        return [{
            "type": "function",
            "function": {
                "name": "save_memory",
                "description": "Save the memory consolidation result to persistent storage.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "history_entry": {
                            "type": "string",
                            "description": "A paragraph summarizing key events/decisions/topics. Start with [YYYY-MM-DD HH:MM].",
                        },
                        "memory_update": {
                            "type": "string",
                            "description": "Updated long-term memory as markdown. Include all existing facts plus new ones.",
                        },
                    },
                    "required": ["history_entry", "memory_update"],
                },
            },
        }]
