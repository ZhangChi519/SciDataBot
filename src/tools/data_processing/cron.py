"""Cron scheduler and task management tools."""
import asyncio
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field
import uuid

from src.tools.base import Tool, ToolResult, ToolCategory


@dataclass
class CronTask:
    """Represents a scheduled cron task."""

    id: str
    name: str
    cron_expression: str
    handler: Callable
    enabled: bool = True
    last_run: Optional[float] = None
    next_run: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class CronParser:
    """Parse cron expressions."""

    # Cron format: minute hour day month weekday
    # Special characters: * , - /

    def __init__(self):
        self._cron_re = re.compile(
            r"^(\*|(\d+(-\d+)?(,\d+(-\d+)?)*))\s+"
            r"(\*|(\d+(-\d+)?(,\d+(-\d+)?)*))\s+"
            r"(\*|(\d+(-\d+)?(,\d+(-\d+)?)*))\s+"
            r"(\*|(\d+(-\d+)?(,\d+(-\d+)?)*))\s+"
            r"(\*|(\d+(-\d+)?(,\d+(-\d+)?)*))$"
        )

    def parse(self, expression: str) -> Dict[str, List[int]]:
        """Parse cron expression into components.

        Args:
            expression: Cron expression (minute hour day month weekday)

        Returns:
            Dict with minute, hour, day, month, weekday lists
        """
        parts = expression.split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression: {expression}")

        return {
            "minute": self._parse_field(parts[0], 0, 59),
            "hour": self._parse_field(parts[1], 0, 23),
            "day": self._parse_field(parts[2], 1, 31),
            "month": self._parse_field(parts[3], 1, 12),
            "weekday": self._parse_field(parts[4], 0, 6),
        }

    def _parse_field(self, field: str, min_val: int, max_val: int) -> List[int]:
        """Parse a single cron field."""
        if field == "*":
            return list(range(min_val, max_val + 1))

        values = set()

        for part in field.split(","):
            if "/" in part:
                # Handle step values (e.g., */5)
                base, step = part.split("/")
                step = int(step)
                if base == "*":
                    start, end = min_val, max_val
                else:
                    start, end = int(base), max_val

                for v in range(start, end + 1, step):
                    values.add(v)
            elif "-" in part:
                # Handle ranges (e.g., 1-5)
                start, end = map(int, part.split("-"))
                values.update(range(start, end + 1))
            else:
                values.add(int(part))

        return sorted(values)

    def get_next_run(self, expression: str) -> Optional[float]:
        """Get next run time for cron expression."""
        import croniter

        try:
            cron = croniter.croniter(expression)
            return cron.get_next()
        except:
            # Fallback calculation
            return None


class CronTool(Tool):
    """Tool for managing scheduled tasks."""

    def __init__(self):
        super().__init__(
            name="cron",
            description="Schedule and manage periodic tasks",
            category=ToolCategory.DATA_PROCESSING,
        )
        self.parser = CronParser()
        self._tasks: Dict[str, CronTask] = {}
        self._running = False
        self._scheduler_task: Optional[asyncio.Task] = None

    async def execute(self, operation: str, **kwargs) -> ToolResult:
        """Execute cron operation."""
        try:
            if operation == "schedule":
                return await self._schedule(
                    kwargs.get("name"),
                    kwargs.get("cron_expression"),
                    kwargs.get("handler_type", "callback"),
                )
            elif operation == "unschedule":
                return await self._unschedule(kwargs.get("task_id"))
            elif operation == "list":
                return await self._list_tasks()
            elif operation == "enable":
                return await self._enable_task(kwargs.get("task_id"))
            elif operation == "disable":
                return await self._disable_task(kwargs.get("task_id"))
            elif operation == "run":
                return await self._run_task(kwargs.get("task_id"))
            else:
                return ToolResult(success=False, error=f"Unknown operation: {operation}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _schedule(
        self,
        name: str,
        cron_expression: str,
        handler_type: str,
    ) -> ToolResult:
        """Schedule a new task."""
        if not name or not cron_expression:
            return ToolResult(success=False, error="Name and cron expression required")

        # Validate cron expression
        try:
            self.parser.parse(cron_expression)
        except ValueError as e:
            return ToolResult(success=False, error=str(e))

        task_id = str(uuid.uuid4())

        # Create a placeholder handler
        async def placeholder_handler():
            print(f"Task {name} executed")

        task = CronTask(
            id=task_id,
            name=name,
            cron_expression=cron_expression,
            handler=placeholder_handler,
        )

        self._tasks[task_id] = task

        return ToolResult(
            success=True,
            data={
                "task_id": task_id,
                "name": name,
                "cron_expression": cron_expression,
            },
        )

    async def _unschedule(self, task_id: str) -> ToolResult:
        """Remove a scheduled task."""
        if task_id in self._tasks:
            del self._tasks[task_id]
            return ToolResult(success=True, data={"task_id": task_id, "removed": True})
        return ToolResult(success=False, error=f"Task not found: {task_id}")

    async def _list_tasks(self) -> ToolResult:
        """List all scheduled tasks."""
        tasks = []
        for task_id, task in self._tasks.items():
            tasks.append({
                "id": task_id,
                "name": task.name,
                "cron_expression": task.cron_expression,
                "enabled": task.enabled,
                "last_run": task.last_run,
            })

        return ToolResult(success=True, data={"tasks": tasks, "count": len(tasks)})

    async def _enable_task(self, task_id: str) -> ToolResult:
        """Enable a task."""
        if task_id in self._tasks:
            self._tasks[task_id].enabled = True
            return ToolResult(success=True, data={"task_id": task_id, "enabled": True})
        return ToolResult(success=False, error=f"Task not found: {task_id}")

    async def _disable_task(self, task_id: str) -> ToolResult:
        """Disable a task."""
        if task_id in self._tasks:
            self._tasks[task_id].enabled = False
            return ToolResult(success=True, data={"task_id": task_id, "enabled": False})
        return ToolResult(success=False, error=f"Task not found: {task_id}")

    async def _run_task(self, task_id: str) -> ToolResult:
        """Manually run a task."""
        if task_id not in self._tasks:
            return ToolResult(success=False, error=f"Task not found: {task_id}")

        task = self._tasks[task_id]

        try:
            result = task.handler()
            if asyncio.iscoroutine(result):
                await result

            task.last_run = time.time()

            return ToolResult(success=True, data={"task_id": task_id, "executed": True})
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def start(self) -> None:
        """Start the cron scheduler."""
        self._running = True
        self._scheduler_task = asyncio.create_task(self._run_scheduler())

    async def stop(self) -> None:
        """Stop the cron scheduler."""
        self._running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass

    async def _run_scheduler(self) -> None:
        """Run the scheduler loop."""
        while self._running:
            now = time.time()

            for task_id, task in self._tasks.items():
                if not task.enabled:
                    continue

                # Check if it's time to run
                if task.next_run and now >= task.next_run:
                    try:
                        result = task.handler()
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception as e:
                        print(f"Error running task {task.name}: {e}")

                    task.last_run = now

                    # Calculate next run time
                    try:
                        import croniter
                        cron = croniter.croniter(task.cron_expression, now)
                        task.next_run = cron.get_next()
                    except:
                        task.next_run = None

            await asyncio.sleep(1)


import time
