"""TUI - Text User Interface for scidatabot."""

import asyncio
import os
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Header, Footer, Static, Input, Label


# CSS 路径
_TUI_DIR = Path(__file__).parent
_CSS_PATH = _TUI_DIR / "tui.tcss"


class ChatScreen(Screen):
    """Main chat screen."""

    BINDINGS = [
        Binding("escape", "app.quit", "Quit"),
    ]

    def __init__(self, scheduler=None, **kwargs):
        super().__init__(**kwargs)
        self.scheduler = scheduler

    def compose(self) -> ComposeResult:
        yield Header()

        # 欢迎信息
        yield Static("""
╔════════════════════════════════════════════════════════════╗
║          scidatabot TUI v1.0                            ║
╠════════════════════════════════════════════════════════════╣
║  欢迎使用 scidatabot 文本界面！                        ║
║                                                            ║
║  功能:                                                     ║
║    - 数据提取与转换                                        ║
║    - 天气查询                                             ║
║    - 文件操作                                             ║
║    - 网络搜索                                             ║
║                                                            ║
║  快捷键:                                                  ║
║    Enter - 发送消息                                       ║
║    Ctrl+L - 清除聊天                                      ║
║    Esc   - 退出程序                                       ║
╚════════════════════════════════════════════════════════════╝
""", id="welcome")

        # 对话区域
        yield Static("", id="chat-history")

        # 输入框
        yield Input(placeholder="输入您的问题或请求，按 Enter 发送...", id="user-input")

        # 状态
        yield Label("[Ready] 等待输入...", id="status")

    def on_mount(self) -> None:
        self.query_one("#user-input").focus()

    async def on_inputSubmitted(self, event) -> None:
        await self._send_message()

    async def _send_message(self) -> None:
        input_widget = self.query_one("#user-input")
        message = input_widget.value.strip()

        if not message:
            return

        input_widget.value = ""

        status = self.query_one("#status")
        status.update(f"[Processing] 正在处理: {message[:30]}...")

        chat = self.query_one("#chat-history")
        chat.update(chat.renderable + f"\n\n[You] {message}")

        try:
            if self.scheduler:
                result = await self.scheduler.execute(message)
                response = result.get("final_report", "任务完成")
            else:
                response = f"收到: {message} (无调度器)"
        except Exception as e:
            response = f"错误: {str(e)}"

        chat.update(chat.renderable + f"\n\n[AI] {response}")
        status.update("[Ready] 完成")


class scidatabotTUI(App):
    """scidatabot TUI 应用"""

    TITLE = "scidatabot"
    SUB_TITLE = "科学数据助手"
    CSS_PATH = str(_CSS_PATH)

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self, scheduler=None, **kwargs):
        super().__init__(**kwargs)
        self.scheduler = scheduler

    def compose(self) -> ComposeResult:
        yield ChatScreen(self.scheduler)

    def action_quit(self) -> None:
        self.exit()


async def run_tui(scheduler=None):
    app = scidatabotTUI(scheduler)
    await app.run_async()


if __name__ == "__main__":
    asyncio.run(run_tui())
