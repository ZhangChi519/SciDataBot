"""MCP (Model Context Protocol) tool integration."""
import asyncio
import json
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from src.tools.base import Tool, ToolResult, ToolCategory


@dataclass
class MCPServer:
    """Represents an MCP server connection."""

    name: str
    command: str
    args: List[str] = None
    env: Dict[str, str] = None
    process: asyncio.subprocess.Process = None


class MCPClient:
    """Client for communicating with MCP servers via JSON-RPC."""

    def __init__(self):
        self._servers: Dict[str, MCPServer] = {}

    async def connect(self, name: str, command: str, args: List[str] = None, env: Dict[str, str] = None) -> None:
        """Connect to an MCP server."""
        server = MCPServer(
            name=name,
            command=command,
            args=args or [],
            env=env or {},
        )

        # Start the server process
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

        # Send JSON-RPC request
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

    async def _send_request(self, server: MCPServer, request: Dict) -> Dict:
        """Send JSON-RPC request to server."""
        request_str = json.dumps(request) + "\n"

        server.process.stdin.write(request_str.encode())
        await server.process.stdin.drain()

        # Read response
        response_line = await server.process.stdout.readline()
        response = json.loads(response_line.decode())

        return response


class MCPTool(Tool):
    """Tool for integrating with MCP (Model Context Protocol) servers."""

    def __init__(self):
        super().__init__(
            name="mcp",
            description="Integrate with MCP (Model Context Protocol) servers",
            category=ToolCategory.DATA_ACCESS,
        )
        self._client = MCPClient()

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

    async def _connect(
        self,
        name: str,
        command: str,
        args: List[str],
        env: Dict[str, str],
    ) -> ToolResult:
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
