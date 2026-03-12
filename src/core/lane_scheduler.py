"""Lane 并发调度器 - 支持真正并行 (增强版)

特性:
- 多 Lane 并行
- 可配置并发数
- 任务队列 + 优先级
- 超时控制
- 错误恢复
- 流式输出
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from enum import Enum
from loguru import logger


class TaskPriority(Enum):
    """任务优先级"""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class LaneConfig:
    """Lane 配置"""
    name: str
    max_concurrent: int = 1
    timeout: float = 300.0
    retry_count: int = 0  # 失败重试次数
    retry_delay: float = 1.0  # 重试延迟(秒)


@dataclass
class QueuedTask:
    """队列任务"""
    id: str
    fn: Callable
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL
    submitted_at: float = 0
    result: Any = None
    error: Optional[str] = None
    retries: int = 0
    cancelled: bool = False


class LaneScheduler:
    """
    车道调度器 (增强版)

    特性：
    - 多 Lane 并行
    - 可配置并发数
    - 优先级队列
    - 超时控制
    - 错误恢复
    - 流式回调
    - 事件驱动
    """

    def __init__(self):
        self.lanes: dict[str, asyncio.PriorityQueue] = {}
        self.lane_configs: dict[str, LaneConfig] = {}
        self.active_tasks: dict[str, set[asyncio.Task]] = {}
        self._running = False
        self._task_counter = 0
        self._lock = asyncio.Lock()

        # 回调
        self.on_task_start: Optional[Callable] = None
        self.on_task_complete: Optional[Callable] = None
        self.on_task_error: Optional[Callable] = None
        self.on_task_progress: Optional[Callable] = None

        # 事件系统
        self.event_handlers: dict[str, Callable] = {}
        self.event_lanes: dict[str, dict] = {}  # event_name -> config

    def register_event(self, event_name: str, handler: Callable, config: dict = None):
        """注册事件处理器
        
        Args:
            event_name: 事件名称
            handler: 事件处理函数
            config: 事件配置 {timeout: 60, timeout_strategy: "react"}
        """
        self.event_handlers[event_name] = handler
        self.event_lanes[event_name] = config or {"timeout": 60, "timeout_strategy": "react"}
        logger.info(f"注册事件: {event_name} (timeout: {self.event_lanes[event_name].get('timeout', 60)}s)")

    async def emit_event(self, event_name: str, *args, **kwargs):
        """触发事件
        
        Args:
            event_name: 事件名称
            *args, **kwargs: 传递给事件处理函数的参数
            
        Returns:
            事件处理结果
        """
        if event_name not in self.event_handlers:
            logger.warning(f"事件未注册: {event_name}")
            return None
        
        config = self.event_lanes.get(event_name, {})
        timeout = config.get("timeout", 60)
        timeout_strategy = config.get("timeout_strategy", "react")
        
        handler = self.event_handlers[event_name]
        
        try:
            result = await asyncio.wait_for(
                handler(*args, **kwargs),
                timeout=timeout
            )
            return result
        except asyncio.TimeoutError:
            logger.warning(f"事件 {event_name} 超时 ({timeout}s)")
            if timeout_strategy == "react":
                # 返回超时信息，让调用方处理
                return {
                    "timeout": True,
                    "event": event_name,
                    "error": f"Event {event_name} timeout after {timeout}s",
                    "timeout_strategy": timeout_strategy
                }
            else:
                raise TimeoutError(f"Event {event_name} timeout after {timeout}s")

    def register_lane(self, config: LaneConfig):
        """注册 Lane"""
        # 使用 PriorityQueue 实现优先级
        self.lanes[config.name] = asyncio.PriorityQueue()
        self.lane_configs[config.name] = config
        self.active_tasks[config.name] = set()
        logger.info(f"注册 Lane: {config.name} (并发: {config.max_concurrent}, 超时: {config.timeout}s)")

    async def submit_task(
        self,
        lane_name: str,
        task_fn: Callable,
        *args,
        **kwargs
    ) -> Any:
        """直接提交任务到Lane并等待执行完成 (简化版)

        Args:
            lane_name: Lane名称
            task_fn: 任务函数
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            任务结果
        """
        if lane_name not in self.lanes:
            raise ValueError(f"Unknown lane: {lane_name}")

        config = self.lane_configs[lane_name]
        
        # 使用信号量控制并发
        if not hasattr(self, '_lane_semaphores'):
            self._lane_semaphores = {}
        
        if lane_name not in self._lane_semaphores:
            self._lane_semaphores[lane_name] = asyncio.Semaphore(config.max_concurrent)
        
        semaphore = self._lane_semaphores[lane_name]
        
        async def bounded_task():
            async with semaphore:
                try:
                    if asyncio.iscoroutinefunction(task_fn):
                        result = await asyncio.wait_for(
                            task_fn(*args, **kwargs),
                            timeout=config.timeout
                        )
                    else:
                        result = task_fn(*args, **kwargs)
                    return result
                except asyncio.TimeoutError:
                    logger.error(f"Lane {lane_name} 任务超时")
                    raise
                except Exception as e:
                    logger.error(f"Lane {lane_name} 任务失败: {e}")
                    raise
        
        return await bounded_task()

    async def enqueue(
        self,
        lane_name: str,
        task_fn: Callable,
        *args,
        priority: TaskPriority = TaskPriority.NORMAL,
        task_id: Optional[str] = None,
        **kwargs
    ) -> QueuedTask:
        """
        加入队列并等待执行

        Args:
            lane_name: Lane 名称
            task_fn: 任务函数
            *args: 位置参数
            priority: 优先级
            task_id: 任务 ID
            **kwargs: 关键字参数

        Returns:
            QueuedTask: 任务对象
        """
        if lane_name not in self.lanes:
            raise ValueError(f"Unknown lane: {lane_name}")

        async with self._lock:
            self._task_counter += 1
            task_id = task_id or f"task_{self._task_counter}"

        task = QueuedTask(
            id=task_id,
            fn=task_fn,
            args=args,
            kwargs=kwargs,
            priority=priority,
            submitted_at=asyncio.get_event_loop().time(),
        )

        # 优先级队列: (priority, submitted_time, task)
        # 优先级取负数实现高优先级先出
        await self.lanes[lane_name].put((-priority.value, task.submitted_at, task))

        logger.debug(f"任务 {task_id} 加入 Lane: {lane_name} (优先级: {priority.name})")

        # 启动消费者(如果未运行)
        if not self._running:
            asyncio.create_task(self.start())

        return task

    async def enqueue_batch(
        self,
        lane_name: str,
        tasks: list[tuple[Callable, tuple, dict]],
        priority: TaskPriority = TaskPriority.NORMAL,
    ) -> list[QueuedTask]:
        """批量加入队列"""
        queued_tasks = []

        for task_fn, args, kwargs in tasks:
            task = await self.enqueue(
                lane_name,
                task_fn,
                *args,
                priority=priority,
                **kwargs
            )
            queued_tasks.append(task)

        return queued_tasks

    async def start(self):
        """启动所有 Lane"""
        self._running = True
        tasks = []

        for lane_name in self.lanes:
            task = asyncio.create_task(self._run_lane(lane_name))
            tasks.append(task)

        logger.info(f"启动了 {len(tasks)} 个 Lane")
        return tasks

    async def stop(self):
        """停止所有 Lane"""
        self._running = False

        # 取消所有活跃任务
        for lane_name, tasks in self.active_tasks.items():
            for task in tasks:
                if not task.done():
                    task.cancel()

    async def cancel_task(self, task_id: str, lane_name: Optional[str] = None):
        """取消指定任务"""
        if lane_name:
            # 取消指定 lane 的任务
            queue = self.lanes.get(lane_name)
            if queue:
                items = []
                while not queue.empty():
                    try:
                        priority, time, task = queue.get_nowait()
                        if task.id == task_id:
                            task.cancelled = True
                            logger.info(f"Task {task_id} cancelled")
                        else:
                            items.append((priority, time, task))
                    except asyncio.QueueEmpty:
                        break

                for item in items:
                    await queue.put(item)
        else:
            # 遍历所有 lane
            for lane_name in self.lanes:
                await self.cancel_task(task_id, lane_name)

    async def cancel_lane(self, lane_name: str):
        """取消指定 lane 的所有任务"""
        queue = self.lanes.get(lane_name)
        if queue:
            # 清空队列
            while not queue.empty():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

            # 取消活跃任务
            for task in self.active_tasks.get(lane_name, set()):
                if not task.done():
                    task.cancel()

    async def _run_lane(self, lane_name: str):
        """运行单个 Lane"""
        config = self.lane_configs[lane_name]
        queue = self.lanes[lane_name]

        while self._running:
            try:
                # 等待任务 (带超时)
                try:
                    priority, submitted_at, task = await asyncio.wait_for(
                        queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                # 检查是否取消
                if task.cancelled:
                    continue

                # 检查并发数
                if len(self.active_tasks[lane_name]) >= config.max_concurrent:
                    # 放回队列，等待槽位
                    await queue.put((priority, submitted_at, task))
                    await asyncio.sleep(0.1)
                    continue

                # 创建任务
                task = asyncio.create_task(
                    self._execute_task(task, lane_name)
                )
                self.active_tasks[lane_name].add(task)
                task.add_done_callback(
                    lambda t, ln=lane_name: self.active_tasks[ln].discard(t)
                )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Lane {lane_name} 错误: {e}")

    async def _execute_task(self, task: QueuedTask, lane_name: str) -> Any:
        """执行任务"""
        config = self.lane_configs[lane_name]

        # 回调: 任务开始
        if self.on_task_start:
            try:
                self.on_task_start(task.id, lane_name)
            except Exception as e:
                logger.warning(f"on_task_start callback error: {e}")

        try:
            logger.debug(f"执行任务: {task.id}")

            # 执行任务 (带超时)
            result = await asyncio.wait_for(
                task.fn(*task.args, **task.kwargs),
                timeout=config.timeout
            )

            task.result = result

            # 回调: 任务完成
            if self.on_task_complete:
                try:
                    self.on_task_complete(task.id, result)
                except Exception as e:
                    logger.warning(f"on_task_complete callback error: {e}")

            return result

        except asyncio.TimeoutError:
            error_msg = f"任务超时 ({config.timeout}s)"
            task.error = error_msg
            logger.warning(f"Task {task.id} timeout")

            # 重试
            if config.retry_count > 0 and task.retries < config.retry_count:
                task.retries += 1
                logger.info(f"Retrying task {task.id}, attempt {task.retries}")
                await asyncio.sleep(config.retry_delay)
                # 重新入队
                await self.lanes[lane_name].put((
                    -task.priority.value,
                    task.submitted_at,
                    task
                ))

            # 回调: 任务错误
            if self.on_task_error:
                try:
                    self.on_task_error(task.id, error_msg)
                except Exception as e:
                    logger.warning(f"on_task_error callback error: {e}")

            raise

        except Exception as e:
            error_msg = str(e)
            task.error = error_msg
            logger.error(f"Task {task.id} failed: {e}")

            # 重试
            if config.retry_count > 0 and task.retries < config.retry_count:
                task.retries += 1
                logger.info(f"Retrying task {task.id}, attempt {task.retries}")
                await asyncio.sleep(config.retry_delay)
                # 重新入队
                await self.lanes[lane_name].put((
                    -task.priority.value,
                    task.submitted_at,
                    task
                ))
            else:
                # 回调: 任务错误
                if self.on_task_error:
                    try:
                        self.on_task_error(task.id, error_msg)
                    except Exception as e:
                        logger.warning(f"on_task_error callback error: {e}")

            raise

    def get_status(self) -> dict:
        """获取状态"""
        status = {}
        for lane_name in self.lanes:
            status[lane_name] = {
                "queue_size": self.lanes[lane_name].qsize(),
                "active_tasks": len(self.active_tasks[lane_name]),
                "max_concurrent": self.lane_configs[lane_name].max_concurrent,
                "timeout": self.lane_configs[lane_name].timeout,
            }
        return status

    def get_task_status(self, task_id: str, lane_name: Optional[str] = None) -> Optional[dict]:
        """获取任务状态"""
        if lane_name:
            queues = {lane_name: self.lanes[lane_name]}
        else:
            queues = self.lanes

        for ln, queue in queues.items():
            for _, _, task in queue.queue:
                if task.id == task_id:
                    return {
                        "id": task.id,
                        "lane": ln,
                        "priority": task.priority.name,
                        "submitted_at": task.submitted_at,
                        "result": task.result,
                        "error": task.error,
                        "retries": task.retries,
                        "cancelled": task.cancelled,
                    }

        # 检查活跃任务
        for ln, tasks in self.active_tasks.items():
            for task in tasks:
                if hasattr(task, 'id') and task.id == task_id:
                    return {
                        "id": task.id,
                        "lane": ln,
                        "status": "running",
                    }

        return None
