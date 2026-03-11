"""MiniMax LLM Provider - 使用 Anthropic 兼容格式."""
import json
import os
from typing import Any, AsyncIterator, Optional

from loguru import logger
from .base import LLMProvider, LLMMessage, LLMTool, LLMResponse, ToolCall


class MiniMaxProvider(LLMProvider):
    """MiniMax LLM provider - 使用 Anthropic 兼容格式."""

    def __init__(
        self,
        model: str = "MiniMax-M2.5",
        api_key: Optional[str] = None,
        base_url: str = "https://api.minimaxi.com/anthropic",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        timeout: float = 60.0,
    ):
        """Initialize MiniMax provider.

        Args:
            model: Model name (e.g., "MiniMax-M2.5").
            api_key: MiniMax API key.
            base_url: Anthropic 兼容 API 端点.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.
            timeout: Request timeout in seconds.
        """
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        self.base_url = base_url
        self.temperature = temperature
        self.max_tokens = max_tokens or 4096
        self.timeout = max(timeout, 120)  # 至少120秒

        if not self.api_key:
            raise ValueError("MiniMax API key is required. Set ANTHROPIC_AUTH_TOKEN env var or pass api_key.")

    async def chat(
        self,
        messages: list[LLMMessage],
        tools: Optional[list[LLMTool]] = None,
        **kwargs,
    ) -> LLMResponse:
        """Send a chat completion request - 使用 Anthropic 兼容格式."""
        import aiohttp

        url = f"{self.base_url}/v1/messages"

        # Convert messages to Anthropic format
        anthropic_messages = []
        system_prompt = None

        for msg in messages:
            # Handle both dict and LLMMessage objects
            if isinstance(msg, dict):
                role = msg.get("role", "user")
                content = msg.get("content", "")
                tool_call_id = msg.get("tool_call_id")
            else:
                role = msg.role
                content = msg.content
                tool_call_id = getattr(msg, 'tool_call_id', None)
            
            if role == "system":
                system_prompt = content
            elif role == "user":
                # Check if this is a tool result message (list content with tool_result type)
                if isinstance(content, list):
                    processed_content = []
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "tool_result":
                            processed_content.append({
                                "type": "tool_result",
                                "tool_use_id": item.get("tool_use_id", tool_call_id or "unknown"),
                                "content": item.get("content", ""),
                            })
                        else:
                            processed_content.append(item)
                    anthropic_messages.append({"role": "user", "content": processed_content})
                else:
                    anthropic_messages.append({"role": "user", "content": content})
            elif role == "assistant":
                # Handle assistant message with potential tool_calls
                if isinstance(msg, dict) and "tool_calls" in msg:
                    msg_content = content or ""
                    tool_calls_list = msg.get("tool_calls", [])
                    
                    blocks = []
                    if msg_content:
                        blocks.append({"type": "text", "text": msg_content})
                    
                    for tc in tool_calls_list:
                        if isinstance(tc, dict):
                            tc_id = tc.get("id", "")
                            func = tc.get("function", {})
                            tc_name = func.get("name", "")
                            tc_args = func.get("arguments", "")
                        else:
                            tc_id = tc.id
                            tc_name = tc.name
                            tc_args = tc.arguments
                        
                        if isinstance(tc_args, str):
                            try:
                                tc_args = json.loads(tc_args)
                            except:
                                tc_args = {}
                        
                        blocks.append({
                            "type": "tool_use",
                            "id": tc_id,
                            "name": tc_name,
                            "input": tc_args,
                        })
                    
                    anthropic_messages.append({"role": "assistant", "content": blocks})
                else:
                    anthropic_messages.append({"role": "assistant", "content": content})
            elif role == "tool":
                anthropic_messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_call_id or "unknown",
                            "content": content,
                        }
                    ],
                })

        # Convert tools to Anthropic format
        anthropic_tools = None
        if tools:
            anthropic_tools = []
            for tool in tools:
                if isinstance(tool, dict):
                    if "function" in tool:
                        func = tool.get("function", {})
                        anthropic_tools.append({
                            "name": func.get("name", ""),
                            "description": func.get("description", ""),
                            "input_schema": func.get("parameters", {}),
                        })
                    else:
                        anthropic_tools.append({
                            "name": tool.get("name", ""),
                            "description": tool.get("description", ""),
                            "input_schema": tool.get("parameters", {}),
                        })
                else:
                    anthropic_tools.append({
                        "name": tool.name,
                        "description": tool.description,
                        "input_schema": tool.parameters,
                    })

        # Build request parameters
        payload = {
            "model": kwargs.get("model", self.model),
            "messages": anthropic_messages,
            "temperature": kwargs.get("temperature", self.temperature),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
        }

        if system_prompt:
            payload["system"] = system_prompt

        if anthropic_tools:
            payload["tools"] = anthropic_tools

        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }

        import certifi

        try:
            os.environ['SSL_CERT_FILE'] = certifi.where()
            os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
        except Exception:
            pass

        timeout = aiohttp.ClientTimeout(total=self.timeout)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"MiniMax API error: {response.status} - {error_text}")

                result = await response.json()

        # Parse response
        content = ""
        tool_calls = None
        has_tool_calls = False

        for block in result.get("content", []):
            block_type = block.get("type", "")
            if block_type == "text":
                content += block.get("text", "")
            elif block_type == "thinking":
                # Skip thinking blocks
                pass
            elif block_type == "tool_use":
                has_tool_calls = True
                if tool_calls is None:
                    tool_calls = []
                tool_calls.append(ToolCall(
                    id=block.get("id", ""),
                    name=block.get("name", ""),
                    arguments=block.get("input", {}),
                ))

        return LLMResponse(
            content=content,
            has_tool_calls=has_tool_calls,
            tool_calls=tool_calls,
            model=result.get("model", self.model),
            usage=result.get("usage", {}),
            finish_reason=result.get("stop_reason"),
        )

    async def stream(
        self,
        messages: list[LLMMessage],
        tools: Optional[list[LLMTool]] = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        """Stream chat completion responses."""
        raise NotImplementedError("Streaming not supported yet in MiniMax provider.")

    async def close(self):
        """Close the client connection."""
        pass

    def get_default_model(self) -> str:
        """Get default model name."""
        return self.model

    @property
    def name(self) -> str:
        return f"minimax-{self.model}"


# Backwards compatibility alias
class MiniMaxAnthropicProvider(MiniMaxProvider):
    """Alias for MiniMaxProvider using Anthropic format."""
    pass
