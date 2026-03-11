#!/usr/bin/env python
"""简单的命令行 TUI - 不依赖 Textual"""

import asyncio
import os
import sys
from pathlib import Path

# 添加路径 - 根据调用方式选择
if __name__ == "__main__":
    # 直接运行时
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
else:
    # 作为模块导入时
    _src_path = Path(__file__).parent.parent / "src"
    if str(_src_path) not in sys.path:
        sys.path.insert(0, str(_src_path))


def print_welcome():
    """打印欢迎界面"""
    print("\033[1;36m" + "=" * 60 + "\033[0m")
    print("\033[1;36m" + "         scidatabot TUI v1.0" + "\033[0m")
    print("\033[1;36m" + "=" * 60 + "\033[0m")
    print()
    print("\033[1;32m欢迎使用 scidatabot 文本界面！\033[0m")
    print()
    print("\033[1;33m功能:\033[0m")
    print("  - 数据提取与转换")
    print("  - 天气查询")
    print("  - 文件操作")
    print("  - 网络搜索")
    print()
    print("\033[1;33m快捷键:\033[0m")
    print("  Ctrl+C - 退出程序")
    print()
    print("\033[1;36m" + "-" * 60 + "\033[0m")
    print()


async def run_simple_tui(scheduler):
    """运行简单 TUI (被 CLI 调用)"""
    print_welcome()

    print("\033[1;32m系统就绪！输入您的问题:\033[0m")
    print()

    while True:
        try:
            # 显示提示符
            print("\033[1;34m>\033[0m ", end="", flush=True)
            message = input()

            if not message.strip():
                continue

            if message.lower() in ["exit", "quit", "退出"]:
                print("\n\033[1;31m再见！\033[0m")
                break

            # 处理消息
            print("\033[90m处理中...\033[0m")

            try:
                result = await scheduler.execute(message)
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


async def main():
    """主函数 (直接运行)"""
    os.chdir(Path(__file__).parent)

    # 打印欢迎
    print_welcome()

    # 加载配置
    from src.cli import load_config
    config = load_config(str(Path(__file__).parent / "config.yaml"))

    # 创建 scheduler，传入配置
    from src.main import create_app
    scheduler = create_app(config)

    await run_simple_tui(scheduler)


if __name__ == "__main__":
    asyncio.run(main())
