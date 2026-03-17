"""Configuration schema using Pydantic."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from pydantic_settings import BaseSettings


class Base(BaseModel):
    """Base model that accepts both camelCase and snake_case keys."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ChannelsConfig(Base):
    """Configuration for chat channels."""

    model_config = ConfigDict(extra="allow")

    send_progress: bool = True
    send_tool_hints: bool = False


class AgentDefaults(Base):
    """Default agent configuration."""

    workspace: str = "~/.scidatabot/workspace"
    model: str = "anthropic/claude-opus-4-5"
    provider: str = "auto"
    max_tokens: int = 8192
    context_window_tokens: int = 65_536
    temperature: float = 0.1
    max_tool_iterations: int = 40
    memory_window: int | None = Field(default=None, exclude=True)
    reasoning_effort: str | None = None


class AgentsConfig(Base):
    """Agent configuration."""

    defaults: AgentDefaults = Field(default_factory=AgentDefaults)


class ProviderConfig(Base):
    """LLM provider configuration."""

    api_key: str = ""
    api_base: str | None = None
    extra_headers: dict[str, str] | None = None


class ProvidersConfig(Base):
    """Configuration for LLM providers."""

    custom: ProviderConfig = Field(default_factory=ProviderConfig)
    azure_openai: ProviderConfig = Field(default_factory=ProviderConfig)
    anthropic: ProviderConfig = Field(default_factory=ProviderConfig)
    openai: ProviderConfig = Field(default_factory=ProviderConfig)
    openrouter: ProviderConfig = Field(default_factory=ProviderConfig)
    deepseek: ProviderConfig = Field(default_factory=ProviderConfig)
    groq: ProviderConfig = Field(default_factory=ProviderConfig)
    zhipu: ProviderConfig = Field(default_factory=ProviderConfig)
    dashscope: ProviderConfig = Field(default_factory=ProviderConfig)
    vllm: ProviderConfig = Field(default_factory=ProviderConfig)
    ollama: ProviderConfig = Field(default_factory=ProviderConfig)
    gemini: ProviderConfig = Field(default_factory=ProviderConfig)
    moonshot: ProviderConfig = Field(default_factory=ProviderConfig)
    minimax: ProviderConfig = Field(default_factory=ProviderConfig)
    aihubmix: ProviderConfig = Field(default_factory=ProviderConfig)
    siliconflow: ProviderConfig = Field(default_factory=ProviderConfig)
    volcengine: ProviderConfig = Field(default_factory=ProviderConfig)
    volcengine_coding_plan: ProviderConfig = Field(default_factory=ProviderConfig)
    byteplus: ProviderConfig = Field(default_factory=ProviderConfig)
    byteplus_coding_plan: ProviderConfig = Field(default_factory=ProviderConfig)
    openai_codex: ProviderConfig = Field(default_factory=ProviderConfig)
    github_copilot: ProviderConfig = Field(default_factory=ProviderConfig)


class HeartbeatConfig(Base):
    """Heartbeat service configuration."""

    enabled: bool = True
    interval_s: int = 30 * 60


class GatewayConfig(Base):
    """Gateway server configuration."""

    host: str = "0.0.0.0"
    port: int = 8080
    heartbeat: HeartbeatConfig = Field(default_factory=HeartbeatConfig)


class ExecToolConfig(Base):
    """Execute tool configuration."""

    enabled: bool = True
    timeout: int = 60
    restrict_to_workspace: bool = True
    path_append: list[str] = Field(default_factory=list)


class WebSearchConfig(Base):
    """Web search tool configuration."""

    enabled: bool = True
    provider: str = "duckduckgo"
    max_results: int = 5
    timeout: int = 30


class WebProxyConfig(Base):
    """Web proxy configuration."""

    enabled: bool = False
    url: str = ""


class ToolsConfig(Base):
    """Tools configuration."""

    exec: ExecToolConfig = Field(default_factory=ExecToolConfig)
    web: WebSearchConfig = Field(default_factory=WebSearchConfig)
    proxy: WebProxyConfig | None = None
    restrict_to_workspace: bool = True
    mcp_servers: dict = Field(default_factory=dict)


class Config(Base):
    """Main configuration."""

    version: int = 1
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)

    @property
    def workspace_path(self) -> Path:
        """Get the workspace path."""
        return Path(self.agents.defaults.workspace).expanduser().resolve()

    def get_provider(self, model: str) -> ProviderConfig | None:
        """Get provider config for a model."""
        provider_name = self.get_provider_name(model)
        return getattr(self.providers, provider_name, None)

    def get_provider_name(self, model: str) -> str:
        """Get provider name from model string."""
        if "/" in model:
            return model.split("/")[0]
        return self.agents.defaults.provider

    def get_api_base(self, model: str) -> str | None:
        """Get API base URL for a model."""
        p = self.get_provider(model)
        if p and p.api_base:
            return p.api_base
        return None
