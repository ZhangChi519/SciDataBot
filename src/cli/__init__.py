"""Command-line interface."""
import asyncio
import sys
import os
from pathlib import Path
from typing import Optional, Annotated

import typer
import yaml
from loguru import logger

from ..config import Config, ConfigManager
from ..channels import ChannelManager, ChannelType
from ..core.agent import GeneralAgent
from ..providers import OpenAIProvider, AnthropicProvider, MockProvider, MiniMaxProvider, GLMProvider
from ..tools import ToolRegistry

app = typer.Typer(help="scidatabot - 科学数据智能助手")

# 获取包目录下的默认配置
# __file__ is src/cli/__init__.py, so we need to go up 3 levels to get to scidatabot/
_PACKAGE_DIR = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
# config.yaml is in scidatabot/ directory (same level as src/)
_DEFAULT_CONFIG = _PACKAGE_DIR / "config.yaml"
# Also check parent directory (for when installed as package)
if not _DEFAULT_CONFIG.exists():
    _DEFAULT_CONFIG = _PACKAGE_DIR.parent / "scidatabot" / "config.yaml"
DEFAULT_CONFIG = str(_DEFAULT_CONFIG)


def setup_logging(log_level: str = "INFO", log_file: Optional[str] = None):
    """Setup logging configuration."""
    logger.remove()

    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )

    logger.add(sys.stderr, format=log_format, level=log_level)

    if log_file:
        logger.add(log_file, format=log_format, level=log_level)


def load_config(config_path: str = DEFAULT_CONFIG) -> dict:
    """Load configuration from YAML file."""
    path = Path(config_path)
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f)
    return {}


def create_llm_provider(config: dict):
    """Create LLM provider from config."""
    provider_type = config.get("llm", {}).get("provider", "minimax")

    if provider_type == "minimax":
        mm_config = config.get("llm", {}).get("minimax", {})
        api_key = mm_config.get("api_key") or os.environ.get("MINIMAX_API_KEY")
        if not api_key:
            typer.echo("Warning: MiniMax API key not set, using MockProvider")
            return MockProvider(model="mock")

        # 检查是否使用 Anthropic 兼容模式
        base_url = mm_config.get("base_url", "")
        if base_url and "anthropic" in base_url:
            # 使用 Anthropic 兼容格式
            return MiniMaxProvider(
                api_key=api_key,
                model=mm_config.get("model", "MiniMax-M2.5"),
                base_url=base_url,
                temperature=mm_config.get("temperature", 0.7),
                max_tokens=mm_config.get("max_tokens", 4096),
                timeout=mm_config.get("timeout", 60),
            )
        else:
            # 使用旧版 OpenAI 兼容格式
            from src.providers.minimax import MiniMaxProvider as OldMiniMaxProvider
            return OldMiniMaxProvider(
                api_key=api_key,
                model=mm_config.get("model", "abab6.5s-chat"),
                base_url=mm_config.get("base_url", "https://api.minimax.chat/v1"),
                temperature=mm_config.get("temperature", 0.7),
                max_tokens=mm_config.get("max_tokens", 4096),
                timeout=mm_config.get("timeout", 60),
            )

    elif provider_type == "anthropic":
        ant_config = config.get("llm", {}).get("anthropic", {})
        api_key = ant_config.get("api_key") or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            typer.echo("Warning: Anthropic API key not set, using MockProvider")
            return MockProvider(model="mock")

        return AnthropicProvider(
            api_key=api_key,
            model=ant_config.get("model", "claude-sonnet-4-20250514"),
            base_url=ant_config.get("base_url"),
            temperature=ant_config.get("temperature", 0.7),
            max_tokens=ant_config.get("max_tokens", 4096),
            timeout=ant_config.get("timeout", 60),
            max_retries=ant_config.get("max_retries", 3),
        )

    elif provider_type == "glm":
        glm_config = config.get("llm", {}).get("glm", {})
        api_key = glm_config.get("api_key") or os.environ.get("ZHIPU_API_KEY") or os.environ.get("GLM_API_KEY")
        if not api_key:
            typer.echo("Warning: GLM API key not set, using MockProvider")
            return MockProvider(model="mock")

        return GLMProvider(
            api_key=api_key,
            model=glm_config.get("model", "glm-4-flash"),
            base_url=glm_config.get("base_url", "https://open.bigmodel.cn/api/paas/v4"),
            temperature=glm_config.get("temperature", 0.7),
            max_tokens=glm_config.get("max_tokens", 4096),
            timeout=glm_config.get("timeout", 60),
        )

    elif provider_type == "custom":
        custom_config = config.get("llm", {}).get("custom", {})
        api_key = custom_config.get("api_key") or os.environ.get("CUSTOM_API_KEY")
        if not api_key:
            typer.echo("Warning: Custom API key not set, using MockProvider")
            return MockProvider(model="mock")

        return OpenAIProvider(
            api_key=api_key,
            model=custom_config.get("model", "gpt-4o"),
            base_url=custom_config.get("base_url"),
            temperature=custom_config.get("temperature", 0.7),
            max_tokens=custom_config.get("max_tokens", 4096),
            timeout=custom_config.get("timeout", 60),
        )

    else:
        typer.echo(f"Unknown provider: {provider_type}, using MockProvider")
        return MockProvider(model="mock")


@app.command()
def run(
    config: Annotated[Optional[str], typer.Option("--config", "-c", help="Config file path")] = None,
    log_level: Annotated[str, typer.Option("--log-level", "-l", help="Log level")] = "INFO",
    provider: Annotated[Optional[str], typer.Option("--provider", "-p", help="LLM provider (override config)")] = None,
    model: Annotated[Optional[str], typer.Option("--model", "-m", help="Model name (override config)")] = None,
    channel: Annotated[Optional[str], typer.Option("--channel", help="Channel to use")] = None,
    confirm_dangerous: Annotated[bool, typer.Option("--confirm-dangerous", help="Automatically confirm dangerous tools")] = False,
):
    """Start the scidatabot."""

    # Load config file
    config_path = config or DEFAULT_CONFIG
    config_data = load_config(config_path)

    # Setup logging
    log_config = config_data.get("logging", {})
    setup_logging(log_level or log_config.get("level", "INFO"), log_config.get("file"))

    # Create LLM provider
    if provider:
        # Override provider from CLI - need to create minimal config
        config_data = {"llm": {"provider": provider}}
        if provider == "minimax":
            config_data["llm"]["minimax"] = {
                "api_key": os.environ.get("MINIMAX_API_KEY") or config_data.get("llm", {}).get("minimax", {}).get("api_key")
            }

    llm = create_llm_provider(config_data)

    # Get provider info
    provider_name = provider or config_data.get("llm", {}).get("provider", "minimax")
    model_name = model or config_data.get("llm", {}).get(provider_name, {}).get("model", "abab6.5s-chat")

    # Create channel manager
    channel_type = channel or config_data.get("channel", {}).get("type", "console")
    channel_manager = ChannelManager()

    if channel_type == "console":
        from ..channels import ConsoleChannel
        channel_manager.add_channel("main", ChannelType.CONSOLE, {})
    else:
        typer.echo(f"Unknown channel: {channel_type}", err=True)
        raise typer.Exit(1)

    # Create workspace and tool registry
    workspace_path = config_data.get("workspace", "./workspace")
    workspace = Path(workspace_path)
    workspace.mkdir(parents=True, exist_ok=True)

    # Create TaskScheduler (same as main.py)
    from ..core.scheduler import TaskScheduler
    from ..core.lane_scheduler import LaneScheduler, LaneConfig
    from ..tools.data_access import FormatDetector, MetadataExtractor, QualityAssessor, WeatherTool
    from ..tools.intent_parser import IntentClassifier, PlanningGenerator
    from ..tools.data_processing import DataExtractor, DataTransformer, DataCleaner, StatisticsAnalyzer
    from ..tools.data_integration import TemporalAligner, SpatialAligner, DataExporter

    # Create Lane scheduler
    lane_scheduler = LaneScheduler()
    lane_scheduler.register_lane(LaneConfig("main", max_concurrent=1, timeout=300))
    lane_scheduler.register_lane(LaneConfig("cron", max_concurrent=2, timeout=600))  # 定时任务
    lane_scheduler.register_lane(LaneConfig("subagent", max_concurrent=8, timeout=300))
    lane_scheduler.register_lane(LaneConfig("nested", max_concurrent=4, timeout=300))  # 嵌套任务
    lane_scheduler.register_lane(LaneConfig("event", max_concurrent=1, timeout=60))  # 事件驱动任务

    # Create tool registry with all tools
    tool_registry = ToolRegistry()

    # Register data access tools
    tool_registry.register(FormatDetector(), "data_access")
    tool_registry.register(MetadataExtractor(), "data_access")
    tool_registry.register(QualityAssessor(), "data_access")
    tool_registry.register(WeatherTool(), "data_access")

    # Register general tools (web search, etc.)
    from src.tools.general import WebSearchTool, WebFetchTool
    web_config = config_data.get("tools", {}).get("web", {})
    tool_registry.register(
        WebSearchTool(api_key=web_config.get("brave_api_key")),
        "general"
    )
    tool_registry.register(WebFetchTool(), "general")

    # Register intent parser tools
    tool_registry.register(IntentClassifier(), "intent_parser")
    tool_registry.register(PlanningGenerator(), "intent_parser")

    # Register data processing tools
    tool_registry.register(DataExtractor(), "data_processing")
    tool_registry.register(DataTransformer(), "data_processing")
    tool_registry.register(DataCleaner(), "data_processing")
    tool_registry.register(StatisticsAnalyzer(), "data_processing")

    # Register data integration tools
    tool_registry.register(TemporalAligner(), "data_integration")
    tool_registry.register(SpatialAligner(), "data_integration")
    tool_registry.register(DataExporter(), "data_integration")

    # Connect MCP servers
    mcp_config = config_data.get("tools", {}).get("mcp_servers", {})
    if mcp_config:
        from src.tools.general import MCPConfig, connect_mcp_servers
        from contextlib import AsyncExitStack
        
        async def connect_mcp():
            stack = AsyncExitStack()
            mcp_servers = {
                name: MCPConfig(
                    command=cfg.get("command"),
                    args=cfg.get("args", []),
                    env=cfg.get("env"),
                    url=cfg.get("url"),
                    headers=cfg.get("headers"),
                    tool_timeout=cfg.get("tool_timeout", 30),
                )
                for name, cfg in mcp_config.items()
            }
            await connect_mcp_servers(mcp_servers, tool_registry, stack)
        
        try:
            asyncio.run(connect_mcp())
        except Exception as e:
            logger.warning(f"Failed to connect MCP servers: {e}")

    # Create confirmation callback for dangerous tools
    async def confirm_dangerous_tool(tool_name: str, arguments: dict) -> bool:
        if confirm_dangerous:
            return True
        typer.echo(f"\n⚠️  危险工具请求: {tool_name}")
        typer.echo(f"   参数: {arguments}")
        response = typer.prompt("   确认执行? (y/n)", default="n")
        return response.lower() in ("y", "yes")

    # Create scheduler
    scheduler = TaskScheduler(
        provider=llm,
        workspace=workspace,
        tool_registry=tool_registry,
        lane_scheduler=lane_scheduler,
        confirm_callback=confirm_dangerous_tool,
    )

    # Message handler - use scheduler
    async def handle_message(message):
        result = await scheduler.execute(message.content)
        return result.get("final_report", "任务完成")

    channel_manager.set_global_handler(handle_message)

    # Start
    typer.echo(f"Starting scidatabot with {provider_name}/{model_name}...")

    try:
        asyncio.run(channel_manager.start_channel("main"))
    except KeyboardInterrupt:
        typer.echo("\nShutting down...")


@app.command()
def tui(
    config: Annotated[Optional[str], typer.Option("--config", "-c", help="Config file path")] = None,
):
    """Start the TUI (Text User Interface)."""
    import asyncio
    from pathlib import Path

    # Load config
    config_path = config or DEFAULT_CONFIG
    config_data = load_config(config_path)

    # Create scheduler using create_app
    from ..main import create_app
    scheduler = create_app(config_data)

    # Import and run simple TUI
    from ..tui.simple_tui import run_simple_tui
    asyncio.run(run_simple_tui(scheduler))


@app.command("skill:list")
def skill_list():
    """List all installed skills."""
    from ..skills.manager import get_skill_loader

    loader = get_skill_loader()
    skills = loader.list()

    if not skills:
        typer.echo("No skills installed.")
        return

    typer.echo(f"Installed skills ({len(skills)}):\n")
    for skill in skills:
        emoji = skill.metadata.emoji or "📦"
        typer.echo(f"  {emoji} {skill.name}")
        if skill.description:
            typer.echo(f"      {skill.description}")
        typer.echo()


@app.command("skill:install")
def skill_install(
    path: str = typer.Argument(..., help="Path to skill directory containing SKILL.md"),
):
    """Install a skill from a local directory."""
    from pathlib import Path
    from ..skills.manager import get_skill_loader

    skill_path = Path(path).expanduser().resolve()

    if not skill_path.exists():
        typer.echo(f"Error: Path does not exist: {skill_path}", err=True)
        raise typer.Exit(1)

    if not skill_path.is_dir():
        typer.echo(f"Error: Path is not a directory: {skill_path}", err=True)
        raise typer.Exit(1)

    skill_file = skill_path / "SKILL.md"
    if not skill_file.exists():
        typer.echo(f"Error: SKILL.md not found in {skill_path}", err=True)
        raise typer.Exit(1)

    loader = get_skill_loader()
    try:
        skill = loader.install(skill_path)
        typer.echo(f"✓ Installed skill: {skill.name}")
    except Exception as e:
        typer.echo(f"Error installing skill: {e}", err=True)
        raise typer.Exit(1)


@app.command("skill:uninstall")
def skill_uninstall(
    name: str = typer.Argument(..., help="Skill name to uninstall"),
):
    """Uninstall a skill."""
    from ..skills.manager import get_skill_loader

    loader = get_skill_loader()

    if loader.uninstall(name):
        typer.echo(f"✓ Uninstalled skill: {name}")
    else:
        typer.echo(f"Error: Could not uninstall skill: {name}", err=True)
        raise typer.Exit(1)


@app.command("skill:info")
def skill_info(
    name: str = typer.Argument(..., help="Skill name"),
):
    """Show detailed info about a skill."""
    from ..skills.manager import get_skill_loader

    loader = get_skill_loader()
    skill = loader.get(name)

    if not skill:
        typer.echo(f"Error: Skill not found: {name}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Skill: {skill.name}")
    typer.echo(f"Description: {skill.description}")
    typer.echo(f"Path: {skill.path}")
    typer.echo(f"Enabled: {skill.enabled}")
    if skill.metadata.emoji:
        typer.echo(f"Emoji: {skill.metadata.emoji}")
    if skill.metadata.homepage:
        typer.echo(f"Homepage: {skill.metadata.homepage}")
    if skill.metadata.requires:
        typer.echo(f"Requires: {skill.metadata.requires}")

    typer.echo("\n--- Content Preview ---")
    # Show first 50 lines
    lines = skill.content.split("\n")[:50]
    typer.echo("\n".join(lines))
    if len(skill.content.split("\n")) > 50:
        typer.echo("\n... (truncated)")


PROVIDER_MODELS = {
    "anthropic": {
        "default": "claude-sonnet-4-20250514",
        "options": ["claude-sonnet-4-20250514", "claude-opus-4-5-20250514", "claude-3-5-sonnet-20241022"],
    },
    "minimax": {
        "default": "MiniMax-M2.5",
        "options": ["MiniMax-M2.5", "abab6.5s-chat"],
    },
    "glm": {
        "default": "glm-4-flash",
        "options": ["glm-4-flash", "glm-4-plus", "glm-4v", "glm-3-turbo"],
    },
    "custom": {
        "default": "custom",
        "options": [],
    },
}


@app.command("connect")
def connect(
    config_path: Annotated[Optional[str], typer.Option("--config", "-c", help="Config file path")] = None,
):
    """Configure API settings interactively."""
    from pathlib import Path
    import yaml

    typer.echo("\n" + "=" * 50)
    typer.echo("  SciDataBot API Configuration")
    typer.echo("=" * 50 + "\n")

    # Load existing config
    cfg_path = config_path or DEFAULT_CONFIG
    config_data = {}
    if Path(cfg_path).exists():
        with open(cfg_path) as f:
            config_data = yaml.safe_load(f) or {}
    
    if "llm" not in config_data:
        config_data["llm"] = {}
    
    # Show current config
    current_provider = config_data.get("llm", {}).get("provider", "minimax")
    typer.echo(f"Current provider: {current_provider}\n")
    
    # Show provider options
    typer.echo("Available providers:")
    typer.echo("  1. anthropic  - Anthropic Claude API")
    typer.echo("  2. minimax   - MiniMax API")
    typer.echo("  3. glm       - Zhipu AI (GLM) API")
    typer.echo("")
    
    # Get provider choice
    provider_choice = typer.prompt(
        "Select provider (1-3)",
        default="2",
        show_default=False,
    )
    
    provider_map = {"1": "anthropic", "2": "minimax", "3": "glm"}
    provider = provider_map.get(provider_choice, "minimax")
    
    typer.echo(f"\nSelected: {provider}")
    
    # Get API key
    env_var_map = {
        "anthropic": "ANTHROPIC_API_KEY",
        "minimax": "MINIMAX_API_KEY",
        "glm": "ZHIPU_API_KEY",
    }
    env_var = env_var_map.get(provider, "API_KEY")
    config_key = config_data.get("llm", {}).get(provider, {}).get("api_key", "")
    current_key = os.environ.get(env_var, "") or config_key
    
    # Mask the API key for display
    display_key = current_key[:10] + "..." if current_key else ""
    
    api_key = typer.prompt(
        f"API Key (env: {env_var})",
        default=current_key,
        show_default=bool(current_key),
        hide_input=True,
    )
    
    if not api_key:
        api_key = current_key
    
    # Get model
    model_info = PROVIDER_MODELS.get(provider, {"default": "gpt-4o"})
    default_model = model_info["default"]
    options = model_info.get("options", [])
    
    if options:
        typer.echo(f"\nAvailable models: {', '.join(options)}")
        model = typer.prompt("Model", default=default_model)
    else:
        model = default_model
    
    # Get temperature
    temp_input = typer.prompt("Temperature (0.0-1.0)", default="0.7", show_default=False)
    try:
        temperature = float(temp_input)
    except ValueError:
        temperature = 0.7
    
    # Get max tokens
    tokens_input = typer.prompt("Max tokens", default="4096", show_default=False)
    try:
        max_tokens = int(tokens_input)
    except ValueError:
        max_tokens = 4096
    
    # Update config
    config_data["llm"]["provider"] = provider
    
    config_data["llm"][provider] = {
        "api_key": api_key,
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if provider == "minimax":
        config_data["llm"][provider]["base_url"] = "https://api.minimaxi.com/anthropic"
    elif provider == "anthropic":
        config_data["llm"][provider]["base_url"] = "https://api.anthropic.com"
    elif provider == "glm":
        config_data["llm"][provider]["base_url"] = "https://open.bigmodel.cn/api/paas/v4"
    
    # Save config
    with open(cfg_path, "w") as f:
        yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True)
    
    typer.echo(f"\n✓ Configuration saved to {cfg_path}")
    typer.echo(f"\nProvider: {provider}")
    typer.echo(f"Model: {model}")
    typer.echo(f"Temperature: {temperature}")
    typer.echo(f"Max tokens: {max_tokens}")
    typer.echo("\nRestart scidatabot to use the new configuration.")
    typer.echo("Run: scidatabot run --config " + cfg_path)


@app.command()
def version():
    """Show version information."""
    typer.echo("scidatabot v0.1.0")


if __name__ == "__main__":
    app()


def main():
    """Entry point for CLI."""
    app()
