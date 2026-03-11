"""LLM Provider 接口"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, List, Optional


@dataclass
class LLMMessage:
    """LLM 消息"""
    role: str  # system, user, assistant, tool
    content: str
    tool_call_id: Optional[str] = None


@dataclass
class LLMTool:
    """LLM 工具定义"""
    name: str
    description: str
    parameters: dict


@dataclass
class ToolCall:
    """工具调用"""
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    """LLM 响应"""
    content: str
    has_tool_calls: bool
    tool_calls: List[ToolCall] = None
    thinking_blocks: list = None
    model: str = None
    usage: dict = None
    finish_reason: str = None

    def __post_init__(self):
        if self.tool_calls is None:
            self.tool_calls = []
        if self.has_tool_calls is None:
            self.has_tool_calls = bool(self.tool_calls)


class LLMProvider(ABC):
    """LLM Provider 基类"""

    @abstractmethod
    async def chat(
        self,
        messages: list,
        tools: list = None,
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs
    ) -> LLMResponse:
        """调用 LLM"""
        pass

    @abstractmethod
    def get_default_model(self) -> str:
        """获取默认模型"""
        pass


class MockProvider(LLMProvider):
    """模拟 Provider - 用于测试"""

    def __init__(self, model: str = "mock"):
        self.model = model
        self.name = "mock"

    async def chat(
        self,
        messages: list,
        tools: list = None,
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs
    ) -> LLMResponse:
        """模拟调用 - 返回简单的响应"""
        # 获取最后一条用户消息
        last_msg = messages[-1].get("content", "") if messages else ""

        # 检查是否有工具可用
        has_tools = tools and len(tools) > 0

        # 简单判断：如果消息包含特定关键词，模拟调用工具
        tool_keywords = ["检测", "提取", "分析", "处理", "转换", "清洗", "统计", "对齐", "导出"]
        should_use_tool = any(kw in last_msg for kw in tool_keywords)

        if has_tools and should_use_tool and tools:
            # 返回一个工具调用
            return LLMResponse(
                content="我将使用工具来处理您的请求。",
                has_tool_calls=True,
                tool_calls=[
                    ToolCall(
                        id="mock_call_1",
                        name=tools[0]["function"]["name"],
                        arguments={"file_path": "/path/to/data.csv"}
                    )
                ]
            )

        return LLMResponse(
            content=f"我收到了您的请求：{last_msg[:100]}...\n\n这是一个模拟响应。在配置好 LLM API 后，我将能够真正处理您的科学数据请求。",
            has_tool_calls=False
        )

    def get_default_model(self) -> str:
        return self.model
