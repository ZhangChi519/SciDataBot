"""通用智能体 - 可配置工具集"""

import asyncio
import json
import uuid
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from loguru import logger


@dataclass
class ExecutionContext:
    """执行上下文 - 智能体间传递"""
    request_id: str
    user_input: str
    intent: dict = field(default_factory=dict)
    task_graph: list = field(default_factory=list)
    data_sources: list = field(default_factory=list)
    access_results: list = field(default_factory=list)
    processing_results: list = field(default_factory=list)
    integration_result: Any = None
    metadata: dict = field(default_factory=dict)
    workspace: str = ""
    system_prompt: str = ""


class GeneralAgent:
    """
    通用智能体

    特性：
    - 可配置的工具集
    - 可自定义系统提示
    - 支持多轮对话
    - 支持子任务
    - 支持进度回调
    - 支持流式输出
    """

    def __init__(
        self,
        name: str,
        provider: "LLMProvider",
        workspace: Path,
        tool_registry: "ToolRegistry",
        system_prompt: str | None = None,
        max_iterations: int = 40,
        temperature: float = 0.7,
        confirm_callback = None,
    ):
        self.name = name
        self.provider = provider
        self.workspace = workspace
        self.tool_registry = tool_registry
        self.system_prompt = system_prompt or self._build_default_prompt()
        self.max_iterations = max_iterations
        self.temperature = temperature
        self.confirm_callback = confirm_callback

    def _build_default_prompt(self) -> str:
        return f"""你是 {self.name}，一个专业的科学数据助手。

你的能力由提供的工具集决定。使用合适的工具来完成用户请求。

## 能力
- 理解科学数据结构
- 分析数据质量
- 处理和转换数据
- 整合多源数据
- 生成分析报告

## 指南
- 在使用工具前，说明你的计划
- 准确描述你需要的参数
- 验证工具返回的结果
- 如果遇到问题，尝试不同方法"""

    # 危险工具列表
    DANGEROUS_TOOLS = {"exec", "write_file", "edit_file", "spawn"}
    
    def _is_dangerous_tool(self, tool_name: str) -> bool:
        """检查是否是危险工具"""
        return tool_name in self.DANGEROUS_TOOLS
    
    async def execute(
        self,
        input_data: str | dict,
        context: ExecutionContext | None = None,
        on_progress: Optional[Callable[[str, bool], None]] = None,
        history: Optional[list[dict]] = None,
    ) -> str:
        """执行任务

        Args:
            input_data: 输入数据
            context: 执行上下文
            on_progress: 进度回调函数 (content, is_tool_hint)
            history: 对话历史消息列表
        """

        # 构建消息
        messages = self._build_messages(input_data, context)

        # 添加历史消息
        if history:
            messages = history + messages

        # ReAct 循环
        iteration = 0
        final_result = None

        while iteration < self.max_iterations:
            iteration += 1

            response = await self.provider.chat(
                messages=messages,
                tools=self.tool_registry.get_definitions(),
                temperature=self.temperature,
            )

            if response.has_tool_calls:
                # 发送进度回调
                if on_progress:
                    clean_content = self._strip_think(response.content)
                    if clean_content:
                        on_progress(clean_content, False)
                        logger.info(f"[{self.name}] 💬 {clean_content[:100]}...")
                    
                    # 发送工具调用提示
                    tool_hint = self._tool_hint(response.tool_calls)
                    if tool_hint:
                        on_progress(tool_hint, True)

                # 添加工具调用到消息
                messages.append({
                    "role": "assistant",
                    "content": response.content or "",
                    "tool_calls": self._format_tool_calls(response.tool_calls),
                })

                # 执行工具
                for tool_call in response.tool_calls:
                    tool_name = tool_call.name
                    args = tool_call.arguments
                    
                    # 构建详细的工具调用日志
                    args_str = ", ".join([f"{k}={repr(v)[:50]}" for k, v in args.items()]) if args else ""
                    logger.info(f"[{self.name}] 🔧 执行工具: {tool_name}({args_str})")
                    
                    # 危险工具确认
                    if self._is_dangerous_tool(tool_name) and self.confirm_callback:
                        confirmed = await self.confirm_callback(tool_name, args)
                        if not confirmed:
                            result = f"✗ 已取消: 工具 '{tool_name}' 被用户拒绝"
                            logger.warning(f"[{self.name}] ❌ 工具 {tool_name} 被用户取消")
                        else:
                            result = await self.tool_registry.execute(
                                tool_name,
                                args,
                            )
                    else:
                        result = await self.tool_registry.execute(
                            tool_name,
                            args,
                        )

                    # 发送进度回调
                    if on_progress:
                        tool_result_hint = f"→ {tool_call.name} 完成"
                        on_progress(tool_result_hint, True)

                    # 添加工具结果
                    messages.append({
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_call.id,
                                "content": result,
                            }
                        ],
                    })
            else:
                # 发送最终内容回调
                if on_progress:
                    clean_content = self._strip_think(response.content)
                    if clean_content:
                        on_progress(clean_content, False)
                
                final_result = response.content
                break

        return final_result or "任务完成"

    def _strip_think(self, content: str) -> Optional[str]:
        """Remove thinking blocks from content."""
        if not content:
            return None
        return re.sub(r"<think>[\s\S]*?</think>", "", content).strip() or None

    def _tool_hint(self, tool_calls: list) -> str:
        """Format tool calls as hint."""
        def fmt(tc):
            args = tc.arguments or {}
            val = next(iter(args.values()), None) if isinstance(args, dict) else None
            if not isinstance(val, str):
                return tc.name
            return f'{tc.name}("{val[:40]}…")' if len(val) > 40 else f'{tc.name}("{val}")'
        return ", ".join(fmt(tc) for tc in tool_calls)

    def _build_messages(self, input_data, context: ExecutionContext | None) -> list:
        """构建消息列表"""
        # 优先使用 context 中的 system_prompt，否则使用默认的
        system_content = context.system_prompt if context and context.system_prompt else self.system_prompt
        
        if context and context.user_input:
            system_content += f"\n\n当前用户输入: {context.user_input}"

        messages = [{"role": "system", "content": system_content}]

        # 添加输入
        if isinstance(input_data, str):
            messages.append({"role": "user", "content": input_data})
        else:
            messages.append({"role": "user", "content": json.dumps(input_data, ensure_ascii=False)})

        return messages

    def _format_tool_calls(self, tool_calls) -> list:
        return [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": json.dumps(tc.arguments, ensure_ascii=False)
                }
            }
            for tc in tool_calls
        ]


# 类型提示
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scidatabot.tools.registry import ToolRegistry
    from scidatabot.providers.base import LLMProvider
