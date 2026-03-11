"""GLM (ZhipuAI) LLM Provider - 使用 OpenAI 兼容格式."""
import json
import os
from typing import Any, AsyncIterator, Optional

from loguru import logger
from .base import LLMProvider, LLMMessage, LLMTool, LLMResponse, ToolCall


class GLMProvider(LLMProvider):
    """GLM (ZhipuAI) LLM provider - 使用 OpenAI 兼容格式."""

    SUPPORTED_MODELS = [
        "glm-4",
        "glm-4-flash",
        "glm-4-plus",
        "glm-4v",
        "glm-4v-flash",
        "glm-3-turbo",
        "glm-4-plus-0520",
        "glm-4-flash-0520",
    ]

    def __init__(
        self,
        model: str = "glm-4-flash",
        api_key: Optional[str] = None,
        base_url: str = "https://open.bigmodel.cn/api/paas/v4",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        timeout: float = 60.0,
    ):
        """Initialize GLM provider.

        Args:
            model: Model name (e.g., "glm-4-flash").
            api_key: GLM API key.
            base_url: API 端点.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.
            timeout: Request timeout in seconds.
        """
        self.model = model
        self.api_key = api_key or os.environ.get("ZHIPU_API_KEY") or os.environ.get("GLM_API_KEY")
        self.base_url = base_url
        self.temperature = temperature
        self.max_tokens = max_tokens or 4096
        self.timeout = timeout

        if not self.api_key:
            raise ValueError("GLM API key is required. Set ZHIPU_API_KEY or GLM_API_KEY env var or pass api_key.")

    async def chat(
        self,
        messages: list[LLMMessage],
        tools: Optional[list[LLMTool]] = None,
        **kwargs,
    ) -> LLMResponse:
        """Send a chat completion request - 使用 OpenAI 兼容格式."""
        import aiohttp

        url = f"{self.base_url}/chat/completions"

        # Convert messages to OpenAI format
        openai_messages = []

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
                openai_messages.append({"role": "system", "content": content})
            elif role == "user":
                # Check if this is a tool result message
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
                    openai_messages.append({"role": "user", "content": processed_content})
                else:
                    openai_messages.append({"role": "user", "content": content})
            elif role == "assistant":
                # Handle assistant message with potential tool_calls
                if isinstance(msg, dict) and "tool_calls" in msg:
                    msg_content = content or ""
                    tool_calls_list = msg.get("tool_calls", [])
                    
                    openai_msg = {"role": "assistant", "content": msg_content}
                    
                    # Add tool calls if present
                    formatted_tool_calls = []
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
                        
                        formatted_tool_calls.append({
                            "id": tc_id,
                            "type": "function",
                            "function": {
                                "name": tc_name,
                                "arguments": json.dumps(tc_args),
                            }
                        })
                    
                    if formatted_tool_calls:
                        openai_msg["tool_calls"] = formatted_tool_calls
                    
                    openai_messages.append(openai_msg)
                else:
                    openai_messages.append({"role": "assistant", "content": content})
            elif role == "tool":
                openai_messages.append({
                    "role": "tool",
                    "content": content,
                    "tool_call_id": tool_call_id or "unknown",
                })

        # Convert tools to OpenAI function format
        openai_tools = None
        if tools:
            openai_tools = []
            for tool in tools:
                if isinstance(tool, dict):
                    if "function" in tool:
                        func = tool.get("function", {})
                        openai_tools.append({
                            "type": "function",
                            "function": {
                                "name": func.get("name", ""),
                                "description": func.get("description", ""),
                                "parameters": func.get("parameters", {}),
                            }
                        })
                    else:
                        openai_tools.append({
                            "type": "function",
                            "function": {
                                "name": tool.get("name", ""),
                                "description": tool.get("description", ""),
                                "parameters": tool.get("parameters", {}),
                            }
                        })
                else:
                    openai_tools.append({
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.parameters,
                        }
                    })

        # Build request parameters
        payload = {
            "model": kwargs.get("model", self.model),
            "messages": openai_messages,
            "temperature": kwargs.get("temperature", self.temperature),
        }

        max_tokens = kwargs.get("max_tokens", self.max_tokens)
        if max_tokens:
            payload["max_tokens"] = max_tokens

        if openai_tools:
            payload["tools"] = openai_tools

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            import certifi
            os.environ['SSL_CERT_FILE'] = certifi.where()
            os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
        except Exception:
            pass

        timeout = aiohttp.ClientTimeout(total=self.timeout)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"GLM API error: {response.status} - {error_text}")

                result = await response.json()

        # Parse response
        content = ""
        tool_calls = None
        has_tool_calls = False

        message = result.get("choices", [{}])[0].get("message", {})
        
        # Handle content
        msg_content = message.get("content", "")
        if msg_content:
            content = msg_content

        # Handle tool calls
        tc_list = message.get("tool_calls", [])
        if tc_list:
            has_tool_calls = True
            tool_calls = []
            for tc in tc_list:
                func = tc.get("function", {})
                tc_args = func.get("arguments", {})
                
                # Parse arguments if it's a string
                if isinstance(tc_args, str):
                    try:
                        tc_args = json.loads(tc_args)
                    except:
                        tc_args = {}
                
                tool_calls.append(ToolCall(
                    id=tc.get("id", ""),
                    name=func.get("name", ""),
                    arguments=tc_args,
                ))

        return LLMResponse(
            content=content,
            has_tool_calls=has_tool_calls,
            tool_calls=tool_calls,
            model=result.get("model", self.model),
            usage=result.get("usage", {}),
            finish_reason=result.get("choices", [{}])[0].get("finish_reason"),
        )

    async def stream(
        self,
        messages: list[LLMMessage],
        tools: Optional[list[LLMTool]] = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        """Stream chat completion responses."""
        raise NotImplementedError("Streaming not supported yet in GLM provider.")

    async def close(self):
        """Close the client connection."""
        pass

    def get_default_model(self) -> str:
        """Get default model name."""
        return self.model

    @property
    def name(self) -> str:
        return f"glm-{self.model}"
