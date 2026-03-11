"""工具基类"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, List, Optional
from enum import Enum


class ToolCategory(Enum):
    """工具类别"""
    DATA_ACCESS = "data_access"
    DATA_PROCESSING = "data_processing"
    DATA_INTEGRATION = "data_integration"
    GENERAL = "general"


@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool
    data: Any = None
    error: str = None

    def __post_init__(self):
        if self.error:
            self.success = False


@dataclass
class ToolSet:
    """工具集"""
    name: str
    description: str
    tools: List["Tool"] = None

    def __post_init__(self):
        if self.tools is None:
            self.tools = []

    def add_tool(self, tool: "Tool"):
        """添加工具"""
        self.tools.append(tool)

    def get_tool(self, name: str) -> Optional["Tool"]:
        """获取工具"""
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None


class Tool(ABC):
    """工具基类"""

    # Default values - subclasses should override
    name: str = "tool"
    description: str = "A tool"
    category: str = "general"

    def __init__(self, name: str = None, description: str = None, category: str = None):
        """Initialize tool with optional properties."""
        if name is not None:
            self.name = name
        if description is not None:
            self.description = description
        if category is not None:
            self.category = category

    @property
    def parameters(self) -> dict:
        """参数 schema"""
        return {
            "type": "object",
            "properties": {},
        }

    @abstractmethod
    async def execute(self, **params) -> ToolResult:
        """执行工具"""
        pass

    def to_schema(self) -> dict:
        """转换为 OpenAI 格式"""
        # 将 snake_case 转换为 PascalCase 作为别名
        pascal_name = "".join(word.capitalize() for word in self.name.split("_"))

        return {
            "type": "function",
            "function": {
                # 主要使用原始名称
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }

    def get_name_variants(self) -> list[str]:
        """获取工具名的所有变体"""
        # snake_case
        variants = [self.name]
        # PascalCase (如 read_file -> ReadFile)
        variants.append("".join(word.capitalize() for word in self.name.split("_")))
        return variants

    def validate_params(self, params: dict) -> bool:
        """验证参数"""
        required = self.parameters.get("required", [])
        for key in required:
            if key not in params:
                return False
        return True
