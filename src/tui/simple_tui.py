#!/usr/bin/env python
"""简单的命令行 TUI - 支持模式切换和命令"""

import asyncio
import os
import sys
from pathlib import Path


def print_welcome(mode="simple"):
    """打印欢迎界面"""
    mode_indicator = "🔬 数据准备模式" if mode == "data_prep" else "💬 简单对话模式"
    
    print("\033[1;36m" + "=" * 60 + "\033[0m")
    print("\033[1;36m" + "         scidatabot TUI v1.0" + "\033[0m")
    print("\033[1;36m" + "=" * 60 + "\033[0m")
    print()
    print(f"\033[1;32m欢迎使用 scidatabot 文本界面！\033[0m")
    print(f"\n当前模式: {mode_indicator}")
    print()
    print("\033[1;33m功能:\033[0m")
    print("  - 数据提取与转换")
    print("  - 天气查询")
    print("  - 文件操作")
    print("  - 网络搜索")
    print()
    print("\033[1;33m快捷键/命令:\033[0m")
    print("  /mode   - 切换模式 (data_prep / simple)")
    print("  /connect - 配置 API 设置")
    print("  /help   - 显示帮助")
    print("  Ctrl+C  - 退出程序")
    print()
    print("\033[1;36m" + "-" * 60 + "\033[0m")
    print()


def get_prefix(mode):
    """获取命令前缀"""
    if mode == "data_prep":
        return "数据准备 "
    return ""


async def run_simple_tui(scheduler, config_path=None):
    """运行简单 TUI (被 CLI 调用)"""
    mode = "simple"
    print_welcome(mode)

    print("\033[1;32m系统就绪！输入您的问题:\033[0m")
    print()

    while True:
        try:
            # 显示提示符
            mode_symbol = "🔬" if mode == "data_prep" else "💬"
            print(f"\033[1;34m{mode_symbol}>\033[0m ", end="", flush=True)
            message = input()

            if not message.strip():
                continue

            # 处理命令
            msg = message.strip().lower()
            
            if msg == "/mode":
                mode = "data_prep" if mode == "simple" else "simple"
                os.system('clear' if os.name == 'posix' else 'cls')
                print_welcome(mode)
                mode_name = "数据准备模式" if mode == "data_prep" else "简单对话模式"
                print(f"\033[1;32m已切换到: {mode_name}\033[0m\n")
                continue
            
            if msg == "/help":
                os.system('clear' if os.name == 'posix' else 'cls')
                print_welcome(mode)
                continue
            
            if msg == "/connect":
                os.system('clear' if os.name == 'posix' else 'cls')
                print_welcome(mode)
                print("\033[1;33m正在启动配置向导...\033[0m\n")
                await run_connect(config_path)
                print()
                continue
            
            if msg in ["exit", "quit", "/quit", "/exit"]:
                print("\n\033[1;31m再见！\033[0m")
                break

            # 构建完整消息
            full_message = get_prefix(mode) + message

            # 处理消息
            print("\033[90m处理中...\033[0m")

            try:
                result = await scheduler.execute(full_message)
                response = result.get("final_report", "任务完成")
            except Exception as e:
                response = f"错误: {str(e)}"

            print()
            print("\033[1;33m回复:\033[0m")
            print(response)
            print()
            print("\033[1;36m" + "-" * 60 + "\033[0m")
            print()

        except KeyboardInterrupt:
            print("\n\n\033[1;31m退出程序\033[0m")
            break
        except EOFError:
            break


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
    
    # 加载现有配置
    if config_path is None:
        config_path = Path(__file__).parent.parent / "config.yaml"
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
    
    api_key = input(f"API Key (env: {env_var}) [默认已保存的]: ").strip()
    if not api_key:
        api_key = provider_key or current_key
    
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
    print("\n\033[1;33m请重新启动 scidatabot 以使用新配置\033[0m")


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
    
    scheduler = create_app(config, confirm_callback=auto_confirm)

    await run_simple_tui(scheduler, str(Path(__file__).parent.parent / "config.yaml"))


if __name__ == "__main__":
    asyncio.run(main())
