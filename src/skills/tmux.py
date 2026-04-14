"""Tmux session management skill."""
import asyncio
from typing import Any, Dict, List, Optional

from src.tools.base import Tool, ToolResult, ToolCategory


class TmuxSkill(Tool):
    """Skill for Tmux terminal session management."""

    name = "tmux"
    description = "Manage Tmux sessions and windows"
    category = ToolCategory.DATA_PROCESSING

    def __init__(self):
        """Initialize tmux skill."""
        pass

    async def execute(self, operation: str, **kwargs) -> ToolResult:
        """Execute tmux operation."""
        try:
            if operation == "list_sessions":
                return await self._list_sessions()
            elif operation == "create_session":
                return await self._create_session(
                    kwargs.get("name"),
                    kwargs.get("command"),
                )
            elif operation == "attach_session":
                return await self._attach_session(kwargs.get("name"))
            elif operation == "send_command":
                return await self._send_command(
                    kwargs.get("session"),
                    kwargs.get("command"),
                )
            elif operation == "kill_session":
                return await self._kill_session(kwargs.get("name"))
            elif operation == "list_windows":
                return await self._list_windows(kwargs.get("session"))
            else:
                return ToolResult(success=False, error=f"Unknown operation: {operation}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _run_tmux(self, args: List[str]) -> str:
        """Run a tmux command."""
        cmd = ["tmux"] + args
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error = stderr.decode()
            raise Exception(f"tmux error: {error}")

        return stdout.decode()

    async def _list_sessions(self) -> ToolResult:
        """List all tmux sessions."""
        try:
            output = await self._run_tmux(["list-sessions", "-F", "#{session_name}"])
            sessions = [s.strip() for s in output.strip().split("\n") if s.strip()]

            return ToolResult(success=True, data={"sessions": sessions, "count": len(sessions)})
        except Exception as e:
            return ToolResult(success=True, data={"sessions": [], "count": 0})

    async def _create_session(self, name: str, command: Optional[str]) -> ToolResult:
        """Create a new tmux session."""
        if not name:
            return ToolResult(success=False, error="Session name is required")

        args = ["new-session", "-d", "-s", name]
        if command:
            args.extend(["-d", command])  # Run command in background

        try:
            await self._run_tmux(args)
            return ToolResult(success=True, data={"session": name, "created": True})
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _attach_session(self, name: str) -> ToolResult:
        """Attach to a tmux session."""
        if not name:
            return ToolResult(success=False, error="Session name is required")

        # Note: This will detach the current session
        try:
            await self._run_tmux(["attach-session", "-t", name])
            return ToolResult(success=True, data={"session": name})
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _send_command(self, session: str, command: str) -> ToolResult:
        """Send command to a tmux session."""
        if not session or not command:
            return ToolResult(success=False, error="Session and command are required")

        try:
            await self._run_tmux(["send-keys", "-t", session, command, "Enter"])
            return ToolResult(success=True, data={"session": session, "command": command})
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _kill_session(self, name: str) -> ToolResult:
        """Kill a tmux session."""
        if not name:
            return ToolResult(success=False, error="Session name is required")

        try:
            await self._run_tmux(["kill-session", "-t", name])
            return ToolResult(success=True, data={"session": name, "killed": True})
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _list_windows(self, session: str) -> ToolResult:
        """List windows in a tmux session."""
        if not session:
            return ToolResult(success=False, error="Session name is required")

        try:
            output = await self._run_tmux(["list-windows", "-t", session, "-F", "#{window_name}"])
            windows = [w.strip() for w in output.strip().split("\n") if w.strip()]

            return ToolResult(success=True, data={"session": session, "windows": windows, "count": len(windows)})
        except Exception as e:
            return ToolResult(success=False, error=str(e))
