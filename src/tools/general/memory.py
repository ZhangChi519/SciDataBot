"""Memory tool - 供 LLM 调用保存记忆"""

from pathlib import Path
from typing import TYPE_CHECKING

from .base import Tool

if TYPE_CHECKING:
    from src.core.memory import MemoryStore


class SaveMemoryTool(Tool):
    """记忆保存工具 - 供 LLM 调用保存长期记忆"""

    name = "save_memory"
    description = "Save the memory consolidation result to persistent storage."
    category = "general"

    def __init__(self, memory_store: "MemoryStore"):
        self.memory_store = memory_store

    @property
    def parameters(self) -> dict:
        return {
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
        }

    async def execute(self, history_entry: str, memory_update: str, **kwargs) -> str:
        """执行记忆保存"""
        try:
            current_memory = self.memory_store.read_long_term()
            
            if history_entry:
                self.memory_store.append_history(history_entry)
            
            if memory_update and memory_update != current_memory:
                self.memory_store.write_long_term(memory_update)
            
            return "Memory saved successfully."
        except Exception as e:
            return f"Error saving memory: {str(e)}"
