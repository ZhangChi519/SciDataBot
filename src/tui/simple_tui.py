#!/usr/bin/env python
"""简单的命令行 TUI - 支持模式切换和命令"""

import asyncio
import os
import sys
from pathlib import Path


def print_welcome(mode="auto"):
    """打印欢迎界面"""
    print("\033[1;36m" + "=" * 60 + "\033[0m")
    print("\033[1;36m" + "         SciDataBot TUI v2.0" + "\033[0m")
    print("\033[1;36m" + "=" * 60 + "\033[0m")
    print()
    print(f"\033[1;32m欢迎使用 SciDataBot 文本界面！\033[0m")
    print(f"\n自动识别任务类型和执行策略")
    print()
    print("\033[1;33m功能:\033[0m")
    print("  - 自动识别任务类型")
    print("  - 简单任务直接执行")
    print("  - 复杂任务并行处理")
    print()
    print("\033[1;33m快捷键/命令:\033[0m")
    print("  /connect - 配置 API 设置")
    print("  /help   - 显示帮助")
    print("  Ctrl+C  - 退出程序")
    print()
    print("\033[1;36m" + "-" * 60 + "\033[0m")
    print()


def get_prefix():
    """获取命令前缀 - 新架构不需要前缀"""
    return ""


async def run_simple_tui(scheduler, config_path=None):
    """运行 TUI (服务模式 - 支持 subagent)"""
    from src.bus.events import InboundMessage, OutboundMessage
    
    print_welcome("auto")
    
    print("\033[1;32m系统就绪！输入您的问题 (输入 exit 退出):\033[0m")
    print("\033[90m模式: 服务模式 (支持后台任务)\033[0m")
    print()
    
    # 用于标记是否正在处理任务
    is_processing = False
    agent_running = False
    
    async def output_listener():
        """监听 outbound bus 并显示结果"""
        nonlocal is_processing
        while True:
            try:
                msg = await asyncio.wait_for(scheduler.bus.consume_outbound(), timeout=0.5)
                if msg and isinstance(msg, OutboundMessage):
                    print()
                    print("\033[1;33m回复:\033[0m")
                    print(msg.content)
                    print()
                    print("\033[1;36m" + "-" * 60 + "\033[0m")
                    print()
                    is_processing = False
            except asyncio.TimeoutError:
                continue
            except Exception:
                break
    
    # 启动输出监听任务
    output_task = asyncio.create_task(output_listener())
    
    # 启动 agent 在后台任务
    async def run_agent():
        nonlocal agent_running
        agent_running = True
        await scheduler.run()
    
    agent_task = asyncio.create_task(run_agent())
    
    # 等待 agent 启动
    await asyncio.sleep(0.5)
    
    try:
        while True:
            # 启用 readline 以改善输入体验
            try:
                import readline
            except ImportError:
                pass
            
            # 设置中文编码
            import sys
            import io
            if sys.stdout.encoding != 'utf-8':
                sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
            
            # 等待用户输入（在线程中执行，避免阻塞事件循环）
            if is_processing:
                print("\033[90m[处理中...] 输入新消息或等待回复\033[0m ", end="", flush=True)
            else:
                print("[SciDataBot] ", end="", flush=True)

            try:
                loop = asyncio.get_event_loop()
                message = await loop.run_in_executor(None, input)
            except (KeyboardInterrupt, EOFError):
                print("\n\033[1;31m退出程序\033[0m")
                break
            
            if not message.strip():
                continue
            
            # 处理命令
            msg = message.strip().lower()
            
            if msg == "/help":
                os.system('clear' if os.name == 'posix' else 'cls')
                print_welcome()
                continue
            
            if msg == "/connect":
                os.system('clear' if os.name == 'posix' else 'cls')
                print_welcome()
                print("\033[1;33m正在启动配置向导...\033[0m\n")
                new_config = await run_connect(config_path)
                # Hot-reload: 用新配置重建 provider 并更新 scheduler
                if new_config:
                    try:
                        from src.cli import create_llm_provider
                        new_provider = create_llm_provider(new_config)
                        scheduler.provider = new_provider
                        new_llm = new_config.get("llm", {})
                        new_prov_type = new_llm.get("provider", "minimax")
                        new_model = new_llm.get(new_prov_type, {}).get("model", scheduler.model)
                        scheduler.model = new_model
                        # 同步更新 subagent_manager 中的 provider / model
                        if hasattr(scheduler, "subagent_manager"):
                            scheduler.subagent_manager.provider = new_provider
                            scheduler.subagent_manager.model = new_model
                        print(f"\033[1;32m✓ 新配置已生效：{new_prov_type} / {new_model}\033[0m\n")
                    except Exception as _e:
                        print(f"\033[1;31m热重载失败，请重启 scidatabot：{_e}\033[0m\n")
                continue
            
            if msg in ["exit", "quit", "/quit", "/exit"]:
                print("\n\033[1;31m再见！\033[0m")
                break
            
            # 等待当前任务完成
            if is_processing:
                print("\033[90m等待当前任务完成...\033[0m")
                continue
            
            # 发送到 bus
            is_processing = True
            inbound_msg = InboundMessage(
                channel="tui",
                sender_id="user",
                chat_id="direct",
                content=message,
            )
            await scheduler.bus.publish_inbound(inbound_msg)

    except KeyboardInterrupt:
        print("\n\033[1;31m退出程序\033[0m")
    except EOFError:
        pass
    finally:
        scheduler.stop()
        output_task.cancel()
        agent_task.cancel()


async def run_connect(config_path=None):
    """运行连接配置向导"""
    import yaml
    import typer
    from typing import Optional
    from typing_extensions import Annotated
    
    PROVIDER_MODELS = {
        "anthropic": {
            "default": "claude-sonnet-4-20250514",
            "options": ["claude-sonnet-4-20250514", "claude-opus-4-5-20250514", "claude-3-5-sonnet-20241022"],
        },
        "minimax": {
            "default": "MiniMax-M2.5",
            "options": ["MiniMax-M2.5", "MiniMax-M2.5-highspeed"],
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
    
    # 加载现有配置
    if config_path is None:
        config_path = Path(__file__).parent.parent.parent / "config.yaml"
    else:
        config_path = Path(config_path)
    
    config_data = {}
    if config_path.exists():
        with open(config_path) as f:
            config_data = yaml.safe_load(f) or {}
    
    if "llm" not in config_data:
        config_data["llm"] = {}
    
    # 显示当前配置
    current_provider = config_data.get("llm", {}).get("provider", "minimax")
    print(f"当前 provider: {current_provider}\n")
    
    # 显示选项
    print("可用 providers:")
    print("  1. anthropic  - Anthropic Claude API")
    print("  2. minimax   - MiniMax API")
    print("  3. glm        - Zhipu AI (GLM) API")
    print("  4. custom     - Custom OpenAI-compatible API")
    print()
    
    # 获取选择
    provider_choice = input("选择 provider (1-4) [默认 2]: ").strip() or "2"
    
    provider_map = {"1": "anthropic", "2": "minimax", "3": "glm", "4": "custom"}
    provider = provider_map.get(provider_choice, "minimax")
    
    print(f"\n已选择: {provider}")
    
    # 获取 API key
    env_var_map = {
        "anthropic": "ANTHROPIC_API_KEY",
        "minimax": "MINIMAX_API_KEY",
        "glm": "ZHIPU_API_KEY",
        "custom": "CUSTOM_API_KEY",
    }
    env_var = env_var_map.get(provider, "API_KEY")
    current_key = os.environ.get(env_var, "")
    
    # 获取当前 provider 的 API key
    provider_key = config_data.get("llm", {}).get(provider, {}).get("api_key", "")
    saved_key = provider_key or current_key

    # 显示已保存 key 的前8位和后4位，帮助用户确认是否正确
    if saved_key and len(saved_key) > 12:
        key_hint = f"{saved_key[:8]}...{saved_key[-4:]}"
    elif saved_key:
        key_hint = saved_key
    else:
        key_hint = "未设置"
    print(f"当前已保存: {key_hint}")

    api_key = input(f"输入新 API Key (直接回车=保留当前值): ").strip()
    if not api_key:
        api_key = saved_key
        print(f"已保留当前 key: {key_hint}")
    
    # 获取模型
    model_info = PROVIDER_MODELS.get(provider, {"default": "gpt-4o"})
    default_model = model_info["default"]
    options = model_info.get("options", [])
    
    if provider == "custom":
        model = input("Model name [默认 gpt-4o]: ").strip() or "gpt-4o"
        base_url = input("Base URL (如 https://api.openai.com/v1): ").strip()
    elif options:
        print(f"\n可用模型: {', '.join(options)}")
        model = input(f"Model [默认 {default_model}]: ").strip() or default_model
    else:
        model = default_model
    
    # 获取温度
    temp_input = input("Temperature (0.0-1.0) [默认 0.7]: ").strip() or "0.7"
    try:
        temperature = float(temp_input)
    except ValueError:
        temperature = 0.7
    
    # 获取 max tokens
    tokens_input = input("Max tokens [默认 4096]: ").strip() or "4096"
    try:
        max_tokens = int(tokens_input)
    except ValueError:
        max_tokens = 4096
    
    # 更新配置
    config_data["llm"]["provider"] = provider
    
    if provider == "custom":
        config_data["llm"]["custom"] = {
            "api_key": api_key,
            "model": model,
            "base_url": base_url,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
    else:
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
    
    # 保存配置
    with open(config_path, "w") as f:
        yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True)

    print(f"\n\033[1;32m✓ 配置已保存到 {config_path}\033[0m")
    print(f"\nProvider: {provider}")
    print(f"Model: {model}")
    print(f"Temperature: {temperature}")
    print(f"Max tokens: {max_tokens}")

    return config_data


async def main():
    """主函数 (直接运行)"""
    import sys
    from pathlib import Path

    # 添加路径
    _src_path = Path(__file__).parent.parent
    if str(_src_path) not in sys.path:
        sys.path.insert(0, str(_src_path))

    os.chdir(Path(__file__).parent.parent)

    # 打印欢迎
    print_welcome("simple")

    # 加载配置
    from src.cli import load_config
    config = load_config(str(Path(__file__).parent.parent / "config.yaml"))

    # 创建 scheduler，传入配置
    from src.main import create_app
    
    async def auto_confirm(tool_name: str, arguments: dict) -> bool:
        print(f"⚠️  危险工具请求: {tool_name}")
        response = input("   确认执行? (y/n): ")
        return response.lower() in ("y", "yes")
    
    scheduler = create_app(config)

    await run_simple_tui(scheduler, str(Path(__file__).parent.parent / "config.yaml"))


if __name__ == "__main__":
    asyncio.run(main())
