"""Anthropic LLM Provider."""
import os
from typing import Any, AsyncIterator, Optional

from .base import LLMProvider, LLMMessage, LLMTool, LLMResponse, ToolCall


class AnthropicProvider(LLMProvider):
    """Anthropic Claude LLM provider."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        timeout: float = 60.0,
        max_retries: int = 3,
    ):
        """Initialize Anthropic provider.

        Args:
            model: Model name (e.g., "claude-sonnet-4-20250514", "claude-opus-4-6-20250514")
            api_key: Anthropic API key. Falls back to ANTHROPIC_API_KEY env var.
            base_url: Custom API base URL for compatible endpoints (e.g., MiniMax).
            temperature: Sampling temperature (0.0 to 1.0).
            max_tokens: Maximum tokens to generate.
            timeout: Request timeout in seconds.
            max_retries: Maximum number of retries on failure.
        """
        try:
            from anthropic import AsyncAnthropic
        except ImportError:
            raise ImportError("anthropic package is required. Install with: pip install anthropic")

        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.base_url = base_url
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.max_retries = max_retries

        if not self.api_key:
            raise ValueError("Anthropic API key is required. Set ANTHROPIC_API_KEY env var.")

        client_kwargs = {
            "api_key": self.api_key,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
        }
        
        if self.base_url:
            client_kwargs["base_url"] = self.base_url

        self._client = AsyncAnthropic(**client_kwargs)

    async def chat(
        self,
        messages: list[LLMMessage],
        tools: Optional[list[LLMTool]] = None,
        **kwargs,
    ) -> LLMResponse:
        """Send a chat completion request.

        Args:
            messages: List of conversation messages.
            tools: Optional list of tools to enable.
            **kwargs: Additional parameters.

        Returns:
            LLMResponse object with content and tool calls.
        """
        # 使用基类方法转换消息和工具
        anthropic_messages, system_prompt = self.convert_messages_anthropic(messages)
        anthropic_tools = self.convert_tools_anthropic(tools)

        # Build request parameters
        params = {
            "model": kwargs.get("model", self.model),
            "messages": anthropic_messages,
            "temperature": kwargs.get("temperature", self.temperature),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
        }

        if system_prompt:
            params["system"] = system_prompt

        if anthropic_tools:
            params["tools"] = anthropic_tools

        # Make request
        response = await self._client.messages.create(**params)

        # Parse response
        content = ""
        tool_calls = None
        has_tool_calls = False

        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                has_tool_calls = True
                if tool_calls is None:
                    tool_calls = []
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input,
                ))

        return LLMResponse(
            content=content,
            has_tool_calls=has_tool_calls,
            tool_calls=tool_calls,
            model=response.model,
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
            finish_reason=response.stop_reason if hasattr(response, 'stop_reason') else None,
        )

    async def stream(
        self,
        messages: list[LLMMessage],
        tools: Optional[list[LLMTool]] = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        """Stream chat completion responses.

        Args:
            messages: List of conversation messages.
            tools: Optional list of tools to enable.
            **kwargs: Additional parameters.

        Yields:
            Content chunks as they arrive.
        """
        anthropic_messages = []
        system_prompt = None

        for msg in messages:
            if msg.role == "system":
                system_prompt = msg.content
            elif msg.role == "user":
                anthropic_messages.append({"role": "user", "content": msg.content})
            elif msg.role == "assistant":
                anthropic_messages.append({"role": "assistant", "content": msg.content})
            elif msg.role == "tool":
                anthropic_messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.tool_call_id,
                            "content": msg.content,
                        }
                    ],
                })

        anthropic_tools = None
        if tools:
            anthropic_tools = []
            for tool in tools:
                anthropic_tools.append({
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.parameters,
                })

        params = {
            "model": kwargs.get("model", self.model),
            "messages": anthropic_messages,
            "temperature": kwargs.get("temperature", self.temperature),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "stream": True,
        }

        if system_prompt:
            params["system"] = system_prompt

        if anthropic_tools:
            params["tools"] = anthropic_tools

        stream = await self._client.messages.create(**params)

        async for chunk in stream:
            if chunk.type == "content_block_delta":
                if chunk.delta.type == "text_delta":
                    yield chunk.delta.text

    async def close(self):
        """Close the client connection."""
        # AsyncAnthropic doesn't need explicit close
        pass

    def get_default_model(self) -> str:
        """Get default model name."""
        return self.model

    @property
    def name(self) -> str:
        return f"anthropic-{self.model}"
