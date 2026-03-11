"""带超时的测试脚本"""
import asyncio
import sys
import os

# 确保使用 venv
venv_python = "/Users/zc-home/Desktop/项目/20260308-openclaw/SciDataBotDev/scidatabot/.venv/bin/python"

async def main():
    # 动态导入并运行
    sys.path.insert(0, "/Users/zc-home/Desktop/项目/20260308-openclaw/SciDataBotDev/scidatabot")
    os.chdir("/Users/zc-home/Desktop/项目/20260308-openclaw/SciDataBotDev/scidatabot")
    
    from src.main import main as app_main
    
    try:
        await asyncio.wait_for(app_main(), timeout=180)
    except asyncio.TimeoutError:
        print("ERROR: 执行超时 (180秒)")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
