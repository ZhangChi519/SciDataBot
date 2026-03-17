"""MCP 客户端工具 - 移植自 nanobot"""

import asyncio
import json
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

try:
    import httpx
except ImportError:
    httpx = None

from src.tools.base import Tool, ToolResult, ToolCategory


@dataclass
class MCPServerInfo:
    """Represents an MCP server connection."""

    name: str
    command: str
    args: List[str] = None
    env: Dict[str, str] = None
    process: asyncio.subprocess.Process = None


class MCPClient:
    """Client for communicating with MCP servers via JSON-RPC."""

    def __init__(self):
        self._servers: Dict[str, MCPServerInfo] = {}

    async def connect(self, name: str, command: str, args: List[str] = None, env: Dict[str, str] = None) -> None:
        """Connect to an MCP server."""
        server = MCPServerInfo(
            name=name,
            command=command,
            args=args or [],
            env=env or {},
        )

        process = await asyncio.create_subprocess_exec(
            command,
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        server.process = process
        self._servers[name] = server

    async def disconnect(self, name: str) -> None:
        """Disconnect from an MCP server."""
        if name in self._servers:
            server = self._servers[name]
            if server.process:
                server.process.terminate()
                await server.process.wait()
            del self._servers[name]

    async def list_tools(self, server_name: str) -> List[Dict]:
        """List available tools on an MCP server."""
        if server_name not in self._servers:
            raise ValueError(f"Server not connected: {server_name}")

        server = self._servers[server_name]

        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
        }

        response = await self._send_request(server, request)

        return response.get("result", {}).get("tools", [])

    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict) -> Any:
        """Call a tool on an MCP server."""
        if server_name not in self._servers:
            raise ValueError(f"Server not connected: {server_name}")

        server = self._servers[server_name]

        request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }

        response = await self._send_request(server, request)

        return response.get("result")

    async def _send_request(self, server: MCPServerInfo, request: Dict) -> Dict:
        """Send JSON-RPC request to server."""
        request_str = json.dumps(request) + "\n"

        server.process.stdin.write(request_str.encode())
        await server.process.stdin.drain()

        response_line = await server.process.stdout.readline()
        response = json.loads(response_line.decode())

        return response


class MCPTool(Tool):
    """Tool for integrating with MCP (Model Context Protocol) servers."""

    name = "mcp"
    description = "Integrate with MCP (Model Context Protocol) servers"
    category = ToolCategory.DATA_ACCESS

    def __init__(self):
        self._client = MCPClient()

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": ["connect", "disconnect", "list_servers", "list_tools", "call"]},
                "name": {"type": "string", "description": "Server name"},
                "command": {"type": "string", "description": "Command to start MCP server"},
                "args": {"type": "array", "items": {"type": "string"}, "description": "Command arguments"},
                "env": {"type": "object", "description": "Environment variables"},
                "tool": {"type": "string", "description": "Tool name to call"},
                "arguments": {"type": "object", "description": "Tool arguments"},
            },
            "required": ["operation"]
        }

    async def execute(self, operation: str, **kwargs) -> ToolResult:
        """Execute MCP operation."""
        try:
            if operation == "connect":
                return await self._connect(
                    kwargs.get("name"),
                    kwargs.get("command"),
                    kwargs.get("args", []),
                    kwargs.get("env", {}),
                )
            elif operation == "disconnect":
                return await self._disconnect(kwargs.get("name"))
            elif operation == "list_servers":
                return await self._list_servers()
            elif operation == "list_tools":
                return await self._list_tools(kwargs.get("name"))
            elif operation == "call":
                return await self._call(
                    kwargs.get("name"),
                    kwargs.get("tool"),
                    kwargs.get("arguments", {}),
                )
            else:
                return ToolResult(success=False, error=f"Unknown operation: {operation}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _connect(self, name: str, command: str, args: List[str], env: Dict[str, str]) -> ToolResult:
        """Connect to an MCP server."""
        try:
            await self._client.connect(name, command, args, env)
            return ToolResult(success=True, data={"name": name, "connected": True})
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _disconnect(self, name: str) -> ToolResult:
        """Disconnect from an MCP server."""
        try:
            await self._client.disconnect(name)
            return ToolResult(success=True, data={"name": name, "disconnected": True})
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _list_servers(self) -> ToolResult:
        """List connected servers."""
        servers = list(self._client._servers.keys())
        return ToolResult(success=True, data={"servers": servers, "count": len(servers)})

    async def _list_tools(self, name: str) -> ToolResult:
        """List tools on a server."""
        try:
            tools = await self._client.list_tools(name)
            return ToolResult(success=True, data={"tools": tools, "count": len(tools)})
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _call(self, name: str, tool: str, arguments: Dict) -> ToolResult:
        """Call a tool on a server."""
        try:
            result = await self._client.call_tool(name, tool, arguments)
            return ToolResult(success=True, data={"result": result})
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class MCPToolWrapper(Tool):
    """Wraps a single MCP server tool as a Tool."""

    def __init__(self, session, server_name: str, tool_def, tool_timeout: int = 30):
        self._session = session
        self._original_name = tool_def.name
        self._name = f"mcp_{server_name}_{tool_def.name}"
        self._description = tool_def.description or tool_def.name
        self._parameters = tool_def.inputSchema or {"type": "object", "properties": {}}
        self._tool_timeout = tool_timeout

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._parameters

    async def execute(self, **kwargs: Any) -> str:
        try:
            from mcp import types
        except ImportError:
            return "Error: mcp package not installed. Install with: pip install mcp"

        try:
            result = await asyncio.wait_for(
                self._session.call_tool(self._original_name, arguments=kwargs),
                timeout=self._tool_timeout,
            )
        except asyncio.TimeoutError:
            return f"(MCP tool call timed out after {self._tool_timeout}s)"
        parts = []
        for block in result.content:
            if isinstance(block, types.TextContent):
                parts.append(block.text)
            else:
                parts.append(str(block))
        return "\n".join(parts) or "(no output)"


class MCPConfig:
    """MCP Server configuration"""
    def __init__(self, command=None, args=None, env=None, url=None, headers=None, tool_timeout=30):
        self.command = command
        self.args = args or []
        self.env = env
        self.url = url
        self.headers = headers
        self.tool_timeout = tool_timeout


async def connect_mcp_servers(mcp_servers: dict, registry, stack: AsyncExitStack) -> None:
    """Connect to configured MCP servers and register their tools."""
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError:
        print("Warning: mcp package not installed. MCP tools will not be available.")
        return

    for name, cfg in mcp_servers.items():
        try:
            if cfg.command:
                params = StdioServerParameters(
                    command=cfg.command, args=cfg.args, env=cfg.env or None
                )
                read, write = await stack.enter_async_context(stdio_client(params))
            elif cfg.url:
                from mcp.client.streamable_http import streamable_http_client
                # Always provide an explicit httpx client so MCP HTTP transport does not
                # inherit httpx's default 5s timeout and preempt the higher-level tool timeout.
                http_client = await stack.enter_async_context(
                    httpx.AsyncClient(
                        headers=cfg.headers or None,
                        follow_redirects=True,
                        timeout=None,
                    )
                )
                read, write, _ = await stack.enter_async_context(
                    streamable_http_client(cfg.url, http_client=http_client)
                )
            else:
                print(f"Warning: MCP server '{name}': no command or url configured, skipping")
                continue

            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()

            tools = await session.list_tools()
            for tool_def in tools.tools:
                wrapper = MCPToolWrapper(session, name, tool_def, tool_timeout=cfg.tool_timeout)
                registry.register(wrapper, "general")
                print(f"MCP: registered tool '{wrapper.name}' from server '{name}'")

            print(f"MCP server '{name}': connected, {len(tools.tools)} tools registered")
        except Exception as e:
            print(f"Error: MCP server '{name}': failed to connect: {e}")
