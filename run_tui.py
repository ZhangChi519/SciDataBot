#!/usr/bin/env python
"""启动 TUI 的脚本"""

import asyncio
import os
import sys

# 添加 src 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.tui import run_tui
from src.main import create_app


async def main():
    print("=" * 50)
    print("启动 scidatabot TUI")
    print("=" * 50)

    # 创建应用
    scheduler = create_app()

    # 运行 TUI
    await run_tui(scheduler)


if __name__ == "__main__":
    asyncio.run(main())
