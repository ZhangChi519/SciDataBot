"""通用工具模块 - 移植自 nanobot"""

from .base import Tool
from .filesystem import ReadFileTool, WriteFileTool, EditFileTool, ListDirTool
from .shell import ExecTool
from .web import WebSearchTool, WebFetchTool
from .message import MessageTool, OutboundMessage
from .spawn import SpawnTool
from .mcp import MCPConfig, connect_mcp_servers, MCPToolWrapper
from .cron import CronTool, CronSchedule
from .registry import GeneralToolRegistry

__all__ = [
    # Base
    "Tool",
    # Filesystem
    "ReadFileTool",
    "WriteFileTool",
    "EditFileTool",
    "ListDirTool",
    # Shell
    "ExecTool",
    # Web
    "WebSearchTool",
    "WebFetchTool",
    # Message
    "MessageTool",
    "OutboundMessage",
    # Spawn
    "SpawnTool",
    # MCP
    "MCPConfig",
    "connect_mcp_servers",
    "MCPToolWrapper",
    # Cron
    "CronTool",
    "CronSchedule",
    # Registry
    "GeneralToolRegistry",
]
