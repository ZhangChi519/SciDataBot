"""流式输出模块 - 支持实时输出和事件流"""

import asyncio
import json
from typing import Any, AsyncIterator, Callable, Optional
from dataclasses import dataclass, field
from enum import Enum
from loguru import logger


class StreamEventType(Enum):
    """流事件类型"""
    START = "start"
    OUTPUT = "output"
    PROGRESS = "progress"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ERROR = "error"
    COMPLETE = "complete"
    CANCELLED = "cancelled"


@dataclass
class StreamEvent:
    """流事件"""
    type: StreamEventType
    data: Any = None
    timestamp: float = field(default_factory=lambda: asyncio.get_event_loop().time())
    run_id: Optional[str] = None
    metadata: dict = field(default_factory=dict)


class StreamOutput:
    """
    流式输出管理器

    支持:
    - 实时 stdout/stderr 捕获
    - 进度更新
    - 工具调用事件
    - 错误事件
    """

    def __init__(self):
        self._listeners: list[asyncio.Queue] = []
        self._buffer: list[StreamEvent] = []
        self._max_buffer_size = 1000

    def add_listener(self) -> asyncio.Queue:
        """添加监听器"""
        queue = asyncio.Queue()
        self._listeners.append(queue)
        return queue

    def remove_listener(self, queue: asyncio.Queue):
        """移除监听器"""
        if queue in self._listeners:
            self._listeners.remove(queue)

    async def emit(self, event: StreamEvent):
        """发射事件"""
        # 缓冲
        self._buffer.append(event)
        if len(self._buffer) > self._max_buffer_size:
            self._buffer.pop(0)

        # 发送给所有监听器
        for queue in self._listeners:
            await queue.put(event)

    async def emit_start(self, run_id: str, message: str = ""):
        """发射开始事件"""
        await self.emit(StreamEvent(
            type=StreamEventType.START,
            data={"message": message},
            run_id=run_id,
        ))

    async def emit_output(self, run_id: str, output: str, is_error: bool = False):
        """发射输出事件"""
        await self.emit(StreamEvent(
            type=StreamEventType.OUTPUT,
            data={"output": output, "is_error": is_error},
            run_id=run_id,
        ))

    async def emit_progress(self, run_id: str, progress: float, message: str = ""):
        """发射进度事件"""
        await self.emit(StreamEvent(
            type=StreamEventType.PROGRESS,
            data={"progress": progress, "message": message},
            run_id=run_id,
        ))

    async def emit_tool_call(self, run_id: str, tool_name: str, args: dict):
        """发射工具调用事件"""
        await self.emit(StreamEvent(
            type=StreamEventType.TOOL_CALL,
            data={"tool": tool_name, "args": args},
            run_id=run_id,
        ))

    async def emit_tool_result(self, run_id: str, tool_name: str, result: str):
        """发射工具结果事件"""
        await self.emit(StreamEvent(
            type=StreamEventType.TOOL_RESULT,
            data={"tool": tool_name, "result": result},
            run_id=run_id,
        ))

    async def emit_error(self, run_id: str, error: str):
        """发射错误事件"""
        await self.emit(StreamEvent(
            type=StreamEventType.ERROR,
            data={"error": error},
            run_id=run_id,
        ))

    async def emit_complete(self, run_id: str, exit_code: int = 0):
        """发射完成事件"""
        await self.emit(StreamEvent(
            type=StreamEventType.COMPLETE,
            data={"exit_code": exit_code},
            run_id=run_id,
        ))

    def get_buffer(self, run_id: Optional[str] = None) -> list[StreamEvent]:
        """获取缓冲区"""
        if run_id:
            return [e for e in self._buffer if e.run_id == run_id]
        return self._buffer.copy()


class StreamProcessor:
    """
    流处理器 - 处理命令输出流

    功能:
    - 实时处理输出
    - 行缓冲
    - JSON 解析
    """

    def __init__(self, buffer_lines: int = 100):
        self.buffer_lines = buffer_lines
        self._buffer: list[str] = []

    async def process_stream(
        self,
        stream: AsyncIterator[str],
        on_line: Optional[Callable[[str], Any]] = None,
    ) -> str:
        """处理流"""
        output_parts = []

        async for line in stream:
            # 缓冲
            self._buffer.append(line)
            if len(self._buffer) > self.buffer_lines:
                self._buffer.pop(0)

            # 输出
            output_parts.append(line)

            # 回调
            if on_line:
                result = on_line(line)
                if result:
                    await self._handle_callback_result(result)

        return "".join(output_parts)

    async def _handle_callback_result(self, result: Any):
        """处理回调结果"""
        if asyncio.iscoroutine(result):
            await result

    def get_buffer(self) -> list[str]:
        """获取缓冲行"""
        return self._buffer.copy()


# 全局流输出
_stream: Optional[StreamOutput] = None


def get_stream_output() -> StreamOutput:
    """获取全局流输出"""
    global _stream
    if _stream is None:
        _stream = StreamOutput()
    return _stream
