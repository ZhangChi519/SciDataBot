"""工具注册表"""

from typing import Any
from .base import Tool


class ToolRegistry:
    """工具注册表 - 支持按类别获取"""

    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._categories: dict[str, set[str]] = {}

    def register(self, tool: Tool, category: str | None = None):
        """注册工具"""
        self._tools[tool.name] = tool

        cat = category or tool.category
        if cat not in self._categories:
            self._categories[cat] = set()
        self._categories[cat].add(tool.name)

    def get(self, name: str) -> Tool | None:
        """获取工具"""
        # 直接查找
        if name in self._tools:
            return self._tools[name]

        # 尝试将 PascalCase 转换为 snake_case (如 ReadFile -> read_file, OpenLines -> open_lines)
        snake_name = "".join(
            ["_" + c.lower() if c.isupper() else c for c in name]
        ).lstrip("_").replace("__", "_")

        if snake_name in self._tools:
            return self._tools[snake_name]

        # 遍历所有工具，尝试匹配 name_variants
        for tool in self._tools.values():
            if name in tool.get_name_variants():
                return tool

        return None

    def get_definitions(self) -> list[dict]:
        """获取所有工具定义"""
        return [tool.to_schema() for tool in self._tools.values()]

    def get_by_category(self, category: str) -> list[Tool]:
        """按类别获取工具"""
        tool_names = self._categories.get(category, set())
        return [self._tools[name] for name in tool_names if name in self._tools]

    def get_subset(self, categories: list[str]) -> "ToolRegistry":
        """获取子集"""
        subset = ToolRegistry()
        for cat in categories:
            for tool in self.get_by_category(cat):
                subset.register(tool, cat)
        return subset

    def list_categories(self) -> list[str]:
        """列出所有类别"""
        return list(self._categories.keys())

    def list_tools(self, category: str | None = None) -> list[str]:
        """列出工具"""
        if category:
            return list(self._categories.get(category, set()))
        return list(self._tools.keys())

    def __len__(self):
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    async def execute(self, name: str, arguments: dict) -> str:
        """执行工具"""
        tool = self.get(name)
        if not tool:
            return f"错误: 未找到工具 {name}"

        try:
            result = await tool.execute(**arguments)
            return str(result) if result is not None else "执行完成"
        except Exception as e:
            return f"错误: {str(e)}"
