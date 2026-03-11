"""命令队列模块 - 速率限制和队列管理"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from enum import Enum
from loguru import logger


class QueuePriority(Enum):
    """队列优先级"""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class QueuedCommand:
    """队列命令"""
    id: str
    func: Callable
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    priority: QueuePriority = QueuePriority.NORMAL
    enqueued_at: float = field(default_factory=time.time)
    result: Any = None
    error: Optional[str] = None
    completed: bool = False
    cancelled: bool = False


class CommandQueue:
    """
    命令队列 - 支持优先级和速率限制

    特性:
    - 优先级队列
    - 速率限制
    - 并发控制
    - 超时处理
    """

    def __init__(
        self,
        max_concurrent: int = 4,
        rate_limit: Optional[int] = None,  # 每秒请求数
        rate_window: float = 1.0,  # 速率窗口(秒)
    ):
        self.max_concurrent = max_concurrent
        self.rate_limit = rate_limit
        self.rate_window = rate_window

        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._active: int = 0
        self._rate_timestamps: list[float] = []
        self._lock = asyncio.Lock()
        self._running = False

    async def enqueue(
        self,
        func: Callable,
        *args,
        priority: QueuePriority = QueuePriority.NORMAL,
        **kwargs
    ) -> QueuedCommand:
        """加入队列"""
        cmd = QueuedCommand(
            id=str(time.time()),
            func=func,
            args=args,
            kwargs=kwargs,
            priority=priority,
        )

        # 优先级取负数(越小越优先)
        await self._queue.put((-priority.value, time.time(), cmd))
        logger.debug(f"Command {cmd.id} enqueued with priority {priority.name}")

        # 启动消费者(如果未运行)
        if not self._running:
            asyncio.create_task(self._consume())

        return cmd

    async def _consume(self):
        """消费队列"""
        self._running = True

        while not self._queue.empty():
            # 检查并发限制
            if self._active >= self.max_concurrent:
                await asyncio.sleep(0.1)
                continue

            # 检查速率限制
            if self.rate_limit:
                if not await self._check_rate_limit():
                    await asyncio.sleep(0.1)
                    continue

            try:
                _, _, cmd = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            if cmd.cancelled:
                continue

            # 执行命令
            self._active += 1
            asyncio.create_task(self._execute(cmd))

        self._running = False

    async def _execute(self, cmd: QueuedCommand):
        """执行命令"""
        try:
            logger.debug(f"Executing command {cmd.id}")
            result = await cmd.func(*cmd.args, **cmd.kwargs)
            cmd.result = result
            cmd.completed = True
        except Exception as e:
            logger.error(f"Command {cmd.id} failed: {e}")
            cmd.error = str(e)
        finally:
            self._active -= 1

    async def _check_rate_limit(self) -> bool:
        """检查速率限制"""
        now = time.time()
        cutoff = now - self.rate_window

        # 清理过期时间戳
        self._rate_timestamps = [t for t in self._rate_timestamps if t > cutoff]

        if len(self._rate_timestamps) >= self.rate_limit:
            return False

        self._rate_timestamps.append(now)
        return True

    def cancel(self, command_id: str):
        """取消命令"""
        # 注意: 这个实现简化了,实际需要遍历队列
        pass

    async def wait_for(self, command: QueuedCommand, timeout: Optional[float] = None) -> Any:
        """等待命令完成"""
        start = time.time()
        while not command.completed and not command.error:
            if timeout and (time.time() - start) > timeout:
                raise TimeoutError(f"Command {command.id} timed out")
            await asyncio.sleep(0.1)

        if command.error:
            raise Exception(command.error)

        return command.result


# 全局队列实例
_queue: Optional[CommandQueue] = None


def get_command_queue(
    max_concurrent: int = 4,
    rate_limit: Optional[int] = None,
) -> CommandQueue:
    """获取全局命令队列"""
    global _queue
    if _queue is None:
        _queue = CommandQueue(max_concurrent, rate_limit)
    return _queue
