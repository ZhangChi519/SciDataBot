"""Shell command execution tool."""
import asyncio
import os
import signal
from typing import Any, List, Optional, Dict
from pathlib import Path

from src.tools.base import Tool, ToolResult, ToolCategory


class ShellTool(Tool):
    """Tool for executing shell commands."""

    def __init__(
        self,
        allowed_commands: Optional[List[str]] = None,
        blocked_commands: Optional[List[str]] = None,
        working_directory: Optional[str] = None,
        timeout: int = 300,
        env: Optional[Dict[str, str]] = None,
    ):
        """Initialize shell tool.

        Args:
            allowed_commands: List of allowed commands (whitelist). If None, all allowed.
            blocked_commands: List of blocked commands (blacklist).
            working_directory: Default working directory.
            timeout: Command timeout in seconds.
            env: Additional environment variables.
        """
        super().__init__(
            name="shell",
            description="Execute shell commands and scripts",
            category=ToolCategory.DATA_PROCESSING,
        )
        self.allowed_commands = allowed_commands
        self.blocked_commands = blocked_commands or [
            "rm -rf /",
            "mkfs",
            "dd if=",
            ":(){:|:&};:",  # Fork bomb
        ]
        self.working_directory = working_directory
        self.timeout = timeout
        self.env = env or {}

    def _validate_command(self, command: str) -> bool:
        """Validate command against whitelist/blacklist."""
        # Check blocked commands
        for blocked in self.blocked_commands:
            if blocked in command:
                return False

        # Check allowed commands
        if self.allowed_commands:
            cmd_base = command.split()[0] if command.split() else ""
            if cmd_base not in self.allowed_commands:
                return False

        return True

    async def execute(self, operation: str, **kwargs) -> ToolResult:
        """Execute shell operation.

        Args:
            operation: Operation type (run, background, kill, list)
            **kwargs: Operation-specific arguments

        Returns:
            ToolResult with operation output
        """
        try:
            if operation == "run":
                return await self._run_command(
                    kwargs.get("command"),
                    kwargs.get("timeout"),
                    kwargs.get("env"),
                )
            elif operation == "background":
                return await self._run_background(
                    kwargs.get("command"),
                    kwargs.get("env"),
                )
            elif operation == "kill":
                return await self._kill_process(kwargs.get("pid"))
            elif operation == "list":
                return await self._list_processes()
            else:
                return ToolResult(success=False, error=f"Unknown operation: {operation}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _run_command(
        self,
        command: str,
        timeout: Optional[int],
        env: Optional[Dict[str, str]],
    ) -> ToolResult:
        """Run a shell command synchronously."""
        if not command:
            return ToolResult(success=False, error="Command is required")

        if not self._validate_command(command):
            return ToolResult(success=False, error="Command not allowed")

        timeout = timeout or self.timeout

        # Merge environment variables
        cmd_env = os.environ.copy()
        cmd_env.update(self.env)
        if env:
            cmd_env.update(env)

        # Set working directory
        cwd = self.working_directory or os.getcwd()

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=cmd_env,
                cwd=cwd,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ToolResult(
                    success=False,
                    error=f"Command timed out after {timeout}s",
                )

            return ToolResult(
                success=process.returncode == 0,
                data={
                    "command": command,
                    "returncode": process.returncode,
                    "stdout": stdout.decode("utf-8", errors="replace"),
                    "stderr": stderr.decode("utf-8", errors="replace"),
                },
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _run_background(
        self,
        command: str,
        env: Optional[Dict[str, str]],
    ) -> ToolResult:
        """Run a shell command in background."""
        if not command:
            return ToolResult(success=False, error="Command is required")

        if not self._validate_command(command):
            return ToolResult(success=False, error="Command not allowed")

        cmd_env = os.environ.copy()
        cmd_env.update(self.env)
        if env:
            cmd_env.update(env)

        cwd = self.working_directory or os.getcwd()

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=cmd_env,
                cwd=cwd,
            )

            return ToolResult(
                success=True,
                data={
                    "command": command,
                    "pid": process.pid,
                    "status": "started",
                },
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _kill_process(self, pid: int) -> ToolResult:
        """Kill a process by PID."""
        try:
            os.kill(pid, signal.SIGTERM)
            return ToolResult(
                success=True,
                data={"pid": pid, "status": "terminated"},
            )
        except ProcessLookupError:
            return ToolResult(success=False, error=f"Process {pid} not found")
        except PermissionError:
            return ToolResult(success=False, error=f"Permission denied to kill {pid}")

    async def _list_processes(self) -> ToolResult:
        """List running processes (simple version)."""
        # This is a simplified version
        return ToolResult(
            success=True,
            data={"message": "Process listing not implemented in this version"},
        )


class REPLTool(Tool):
    """Tool for executing Python code in a REPL."""

    def __init__(self, timeout: int = 60):
        super().__init__(
            name="python",
            description="Execute Python code",
            category=ToolCategory.DATA_PROCESSING,
        )
        self.timeout = timeout

    async def execute(self, operation: str, **kwargs) -> ToolResult:
        """Execute Python code."""
        try:
            if operation == "run":
                return await self._run_code(kwargs.get("code"))
            else:
                return ToolResult(success=False, error=f"Unknown operation: {operation}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _run_code(self, code: str) -> ToolResult:
        """Run Python code."""
        if not code:
            return ToolResult(success=False, error="Code is required")

        # Use exec in a restricted globals dict
        restricted_globals = {
            "__builtins__": {
                "print": print,
                "len": len,
                "str": str,
                "int": int,
                "float": float,
                "list": list,
                "dict": dict,
                "tuple": tuple,
                "set": set,
                "range": range,
                "enumerate": enumerate,
                "zip": zip,
                "map": map,
                "filter": filter,
                "sum": sum,
                "min": min,
                "max": max,
                "abs": abs,
                "round": round,
                "sorted": sorted,
                "reversed": reversed,
                "any": any,
                "all": all,
                "isinstance": isinstance,
                "type": type,
            },
        }

        local_vars = {}
        output = []

        # Capture print output
        def custom_print(*args, **kwargs):
            output.append(" ".join(str(a) for a in args))

        restricted_globals["__builtins__"]["print"] = custom_print

        try:
            exec(code, restricted_globals, local_vars)

            return ToolResult(
                success=True,
                data={
                    "stdout": "\n".join(output),
                    "variables": {k: str(v) for k, v in local_vars.items()},
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Execution error: {str(e)}",
            )
