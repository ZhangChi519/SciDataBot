"""定时任务工具 - 移植自 nanobot (兼容版)"""

from contextvars import ContextVar
from typing import Any

from .base import Tool


class CronSchedule:
    """Cron schedule definition"""
    def __init__(self, kind: str, every_ms: int = None, expr: str = None, tz: str = None, at_ms: int = None):
        self.kind = kind
        self.every_ms = every_ms
        self.expr = expr
        self.tz = tz
        self.at_ms = at_ms


class CronTool(Tool):
    """Tool to schedule reminders and recurring tasks."""

    def __init__(self, cron_service=None):
        self._cron = cron_service
        self._channel = ""
        self._chat_id = ""
        self._in_cron_context: ContextVar[bool] = ContextVar("cron_in_context", default=False)

    def set_context(self, channel: str, chat_id: str) -> None:
        """Set the current session context for delivery."""
        self._channel = channel
        self._chat_id = chat_id

    def set_cron_context(self, active: bool):
        """Mark whether the tool is executing inside a cron job callback."""
        return self._in_cron_context.set(active)

    def reset_cron_context(self, token) -> None:
        """Restore previous cron context."""
        self._in_cron_context.reset(token)

    @property
    def name(self) -> str:
        return "cron"

    @property
    def description(self) -> str:
        return "Schedule reminders and recurring tasks. Actions: add, list, remove."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "list", "remove"],
                    "description": "Action to perform",
                },
                "message": {"type": "string", "description": "Reminder message (for add)"},
                "every_seconds": {
                    "type": "integer",
                    "description": "Interval in seconds (for recurring tasks)",
                },
                "cron_expr": {
                    "type": "string",
                    "description": "Cron expression like '0 9 * * *' (for scheduled tasks)",
                },
                "tz": {
                    "type": "string",
                    "description": "IANA timezone for cron expressions (e.g. 'America/Vancouver')",
                },
                "at": {
                    "type": "string",
                    "description": "ISO datetime for one-time execution (e.g. '2026-02-12T10:30:00')",
                },
                "job_id": {"type": "string", "description": "Job ID (for remove)"},
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        message: str = "",
        every_seconds: int | None = None,
        cron_expr: str | None = None,
        tz: str | None = None,
        at: str | None = None,
        job_id: str | None = None,
        **kwargs: Any,
    ) -> str:
        if not self._cron:
            return "Error: Cron service not configured. Please provide a cron_service."

        if action == "add":
            if self._in_cron_context.get():
                return "Error: cannot schedule new jobs from within a cron job execution"
            return self._add_job(message, every_seconds, cron_expr, tz, at)
        elif action == "list":
            return self._list_jobs()
        elif action == "remove":
            return self._remove_job(job_id)
        return f"Unknown action: {action}"

    def _add_job(
        self,
        message: str,
        every_seconds: int | None,
        cron_expr: str | None,
        tz: str | None,
        at: str | None,
    ) -> str:
        if not message:
            return "Error: message is required for add"
        if not self._channel or not self._chat_id:
            return "Error: no session context (channel/chat_id)"
        if tz and not cron_expr:
            return "Error: tz can only be used with cron_expr"
        if tz:
            try:
                from zoneinfo import ZoneInfo
                ZoneInfo(tz)
            except (KeyError, Exception):
                return f"Error: unknown timezone '{tz}'"

        # Build schedule
        delete_after = False
        if every_seconds:
            schedule = CronSchedule(kind="every", every_ms=every_seconds * 1000)
        elif cron_expr:
            schedule = CronSchedule(kind="cron", expr=cron_expr, tz=tz)
        elif at:
            from datetime import datetime
            dt = datetime.fromisoformat(at)
            at_ms = int(dt.timestamp() * 1000)
            schedule = CronSchedule(kind="at", at_ms=at_ms)
            delete_after = True
        else:
            return "Error: either every_seconds, cron_expr, or at is required"

        try:
            job = self._cron.add_job(
                name=message[:30],
                schedule=schedule,
                message=message,
                deliver=True,
                channel=self._channel,
                to=self._chat_id,
                delete_after_run=delete_after,
            )
            return f"Created job '{job.name}' (id: {job.id})"
        except AttributeError:
            return "Error: Cron service does not support add_job. Please use the data_processing.CronTool instead."
        except Exception as e:
            return f"Error adding job: {str(e)}"

    def _list_jobs(self) -> str:
        try:
            jobs = self._cron.list_jobs()
            if not jobs:
                return "No scheduled jobs."
            lines = [f"- {j.name} (id: {j.id}, {j.schedule.kind})" for j in jobs]
            return "Scheduled jobs:\n" + "\n".join(lines)
        except AttributeError:
            return "Error: Cron service does not support list_jobs."
        except Exception as e:
            return f"Error listing jobs: {str(e)}"

    def _remove_job(self, job_id: str | None) -> str:
        if not job_id:
            return "Error: job_id is required for remove"
        try:
            if self._cron.remove_job(job_id):
                return f"Removed job {job_id}"
            return f"Job {job_id} not found"
        except AttributeError:
            return "Error: Cron service does not support remove_job."
        except Exception as e:
            return f"Error removing job: {str(e)}"
