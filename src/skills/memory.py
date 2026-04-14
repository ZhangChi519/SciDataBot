"""Memory skill for storing and retrieving conversation context."""
from typing import Any, Dict, List, Optional

from src.tools.base import Tool, ToolResult, ToolCategory


class MemorySkill(Tool):
    """Skill for persistent memory storage."""

    name = "memory"
    description = "Store and retrieve persistent memories"
    category = ToolCategory.DATA_PROCESSING

    def __init__(self, storage=None):
        """Initialize memory skill."""
        self._storage = storage or {}
        self._index = {}

    async def execute(self, operation: str, **kwargs) -> ToolResult:
        """Execute memory operation."""
        try:
            if operation == "store":
                return await self._store(
                    kwargs.get("key"),
                    kwargs.get("value"),
                    kwargs.get("metadata"),
                )
            elif operation == "retrieve":
                return await self._retrieve(kwargs.get("key"))
            elif operation == "search":
                return await self._search(kwargs.get("query"))
            elif operation == "delete":
                return await self._delete(kwargs.get("key"))
            elif operation == "list":
                return await self._list(kwargs.get("prefix"))
            elif operation == "clear":
                return await self._clear()
            else:
                return ToolResult(success=False, error=f"Unknown operation: {operation}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _store(self, key: str, value: Any, metadata: Optional[Dict]) -> ToolResult:
        """Store a memory."""
        if not key:
            return ToolResult(success=False, error="Key is required")

        self._storage[key] = {
            "value": value,
            "metadata": metadata or {},
        }

        # Update index
        key_lower = key.lower()
        for word in key_lower.split():
            if word not in self._index:
                self._index[word] = []
            if key not in self._index[word]:
                self._index[word].append(key)

        return ToolResult(success=True, data={"key": key, "stored": True})

    async def _retrieve(self, key: str) -> ToolResult:
        """Retrieve a memory."""
        if key in self._storage:
            return ToolResult(
                success=True,
                data=self._storage[key],
            )
        return ToolResult(success=False, error=f"Key not found: {key}")

    async def _search(self, query: str) -> ToolResult:
        """Search memories."""
        query_lower = query.lower()
        results = []

        for word in query_lower.split():
            if word in self._index:
                for key in self._index[word]:
                    if key not in results:
                        results.append(key)

        memories = [self._storage.get(k) for k in results if k in self._storage]

        return ToolResult(success=True, data={"results": memories, "count": len(memories)})

    async def _delete(self, key: str) -> ToolResult:
        """Delete a memory."""
        if key in self._storage:
            # Clean up index
            key_lower = key.lower()
            for word in key_lower.split():
                if word in self._index:
                    self._index[word].discard(key)
                    if not self._index[word]:
                        del self._index[word]
            
            del self._storage[key]
            return ToolResult(success=True, data={"key": key, "deleted": True})
        return ToolResult(success=False, error=f"Key not found: {key}")

    async def _list(self, prefix: str = "") -> ToolResult:
        """List all keys."""
        keys = list(self._storage.keys())
        if prefix:
            keys = [k for k in keys if k.startswith(prefix)]
        return ToolResult(success=True, data={"keys": keys, "count": len(keys)})

    async def _clear(self) -> ToolResult:
        """Clear all memories."""
        self._storage.clear()
        self._index.clear()
        return ToolResult(success=True, data={"cleared": True})
