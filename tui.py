#!/usr/bin/env python3
"""SciDataBot TUI - 支持Tab切换数据准备/简单模式"""

import asyncio
import os
import sys
from pathlib import Path

# 添加src到路径
sys.path.insert(0, str(Path(__file__).parent))


class SimpleTUI:
    """简单的TUI界面，支持Tab切换模式"""
    
    def __init__(self, scheduler):
        self.scheduler = scheduler
        self.mode = "simple"  # simple 或 data_prep
        self.running = True
        self.history = []
        self.history_index = -1
    
    def clear_screen(self):
        """清屏"""
        os.system('clear' if os.name == 'posix' else 'cls')
    
    def print_header(self):
        """打印头部"""
        print("\033[1;36m" + "=" * 60 + "\033[0m")
        print(f"\033[1;36m  SciDataBot TUI v2.0 (新架构)\033[0m")
        print("\033[1;36m" + "=" * 60 + "\033[0m")
        print("\n自动识别任务类型和执行策略")
        print("\n快捷键:")
        print("  /quit - 退出程序")
        print("  /help - 显示帮助")
        print("\033[1;36m" + "-" * 60 + "\033[0m\n")
    
    def get_prefix(self):
        """获取命令前缀 - 新架构不需要前缀"""
        return ""
    
    def process_command(self, message):
        """处理特殊命令"""
        msg = message.strip().lower()
        
        # 移除 /mode 命令 - 现在自动判断
        # if msg == "/mode":
        #     ...
        
        if msg == "/help":
            self.print_header()
            return True
        
        if msg in ["/quit", "/exit"]:
            print("\n\033[1;31m再见！\033[0m")
            self.running = False
            return True
        
        return False
    
    async def run(self):
        """运行TUI"""
        self.clear_screen()
        self.print_header()
        
        print("\033[1;32m系统就绪！输入您的请求:\033[0m\n")
        
        while self.running:
            try:
                # 显示提示符
                mode_symbol = "数据" if self.mode == "data_prep" else "聊天"
                print(f"[{mode_symbol}] ", end="", flush=True)
                
                # 读取输入
                message = input()
                
                if not message.strip():
                    continue
                
                # 处理特殊命令
                if message.strip().startswith('/') or message.strip().lower() in ['exit', 'quit', '退出']:
                    if self.process_command(message):
                        continue
                
                # 添加到历史
                self.history.append(message)
                self.history_index = len(self.history)
                
                # 构建完整消息
                full_message = self.get_prefix() + message
                
                # 处理消息
                print("\033[90m处理中...\033[0m")
                
                try:
                    result = await self.scheduler.execute(full_message)
                    response = result.get("final_report", "任务完成")
                except Exception as e:
                    response = f"错误: {str(e)}"
                
                print()
                print("\033[1;33m回复:\033[0m")
                print(response)
                print()
                print("\033[1;36m" + "-" * 60 + "\033[0m")
                
            except KeyboardInterrupt:
                print("\n\n\033[1;31m退出程序\033[0m")
                break
            except EOFError:
                break


async def main():
    """主函数"""
    from src.cli import load_config
    from src.main import create_app
    
    # 加载配置
    config_path = Path(__file__).parent / "config.yaml"
    config = load_config(str(config_path))
    
    # 创建scheduler
    scheduler = create_app(config)
    
    # 运行TUI
    tui = SimpleTUI(scheduler)
    await tui.run()


if __name__ == "__main__":
    asyncio.run(main())
