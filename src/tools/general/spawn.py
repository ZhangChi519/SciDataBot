"""Spawn 工具 - 移植自 nanobot (简化版)"""

from typing import Any

from .base import Tool


class SpawnTool(Tool):
    """Tool to spawn a subagent for background task execution."""

    def __init__(self, subagent_callback=None):
        self._subagent_callback = subagent_callback
        self._origin_channel = "cli"
        self._origin_chat_id = "direct"
        self._session_key = "cli:direct"

    def set_context(self, channel: str, chat_id: str) -> None:
        """Set the origin context for subagent announcements."""
        self._origin_channel = channel
        self._origin_chat_id = chat_id
        self._session_key = f"{channel}:{chat_id}"

    @property
    def name(self) -> str:
        return "spawn"

    @property
    def description(self) -> str:
        return (
            "Spawn a taskplanner subagent to handle the user request. "
            "ALWAYS spawn first for any request. "
            "The taskplanner will decide how to process the task."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The task for the subagent to complete",
                },
                "label": {
                    "type": "string",
                    "description": "Optional short label for the task (for display)",
                },
            },
            "required": ["task"],
        }

    async def execute(self, task: str, label: str | None = None, **kwargs: Any) -> str:
        """Spawn a subagent to execute the given task."""
        if not self._subagent_callback:
            return "Error: Subagent spawning not configured. Please provide a subagent_callback."

        try:
            return await self._subagent_callback(
                task=task,
                label=label,
                origin_channel=self._origin_channel,
                origin_chat_id=self._origin_chat_id,
                session_key=self._session_key,
            )
        except NotImplementedError:
            return "Error: Subagent spawning is not yet implemented in this environment."
        except Exception as e:
            return f"Error spawning subagent: {str(e)}"
