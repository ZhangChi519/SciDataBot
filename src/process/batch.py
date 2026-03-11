"""批量处理模块 - 支持并行任务和流式输出"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, AsyncIterator, Optional
from enum import Enum

from loguru import logger


class BatchStrategy(Enum):
    """批量处理策略"""
    SEQUENTIAL = "sequential"    # 顺序执行
    PARALLEL = "parallel"        # 完全并行
    LIMITED = "limited"          # 限制并发数


@dataclass
class BatchItem:
    """批量处理项"""
    id: str
    data: Any
    result: Any = None
    error: Optional[str] = None
    status: str = "pending"  # pending, running, completed, failed


@dataclass
class BatchResult:
    """批量处理结果"""
    strategy: BatchStrategy
    items: list[BatchItem]
    total: int = 0
    completed: int = 0
    failed: int = 0
    duration_ms: float = 0


class BatchProcessor:
    """
    批量处理器

    支持:
    - 顺序处理
    - 并行处理
    - 限制并发数
    - 流式输出
    - 错误恢复
    """

    def __init__(self, max_concurrent: int = 4):
        self.max_concurrent = max_concurrent

    async def process(
        self,
        items: list[Any],
        processor: Callable[[Any], Any],
        strategy: BatchStrategy = BatchStrategy.LIMITED,
        on_progress: Optional[Callable[[BatchItem], None]] = None,
    ) -> BatchResult:
        """
        批量处理

        Args:
            items: 要处理的项目列表
            processor: 处理函数 (async)
            strategy: 处理策略
            on_progress: 进度回调
        """
        import time
        start_time = time.time()

        batch_items = [
            BatchItem(id=str(i), data=item)
            for i, item in enumerate(items)
        ]

        if strategy == BatchStrategy.SEQUENTIAL:
            results = await self._process_sequential(batch_items, processor, on_progress)
        elif strategy == BatchStrategy.PARALLEL:
            results = await self._process_parallel(batch_items, processor, on_progress)
        else:  # LIMITED
            results = await self._process_limited(batch_items, processor, on_progress)

        duration_ms = (time.time() - start_time) * 1000

        completed = sum(1 for r in results if r.status == "completed")
        failed = sum(1 for r in results if r.status == "failed")

        return BatchResult(
            strategy=strategy,
            items=results,
            total=len(items),
            completed=completed,
            failed=failed,
            duration_ms=duration_ms,
        )

    async def _process_sequential(
        self,
        items: list[BatchItem],
        processor: Callable,
        on_progress: Optional[Callable],
    ) -> list[BatchItem]:
        """顺序处理"""
        results = []
        for item in items:
            item.status = "running"
            try:
                result = await processor(item.data)
                item.result = result
                item.status = "completed"
            except Exception as e:
                item.error = str(e)
                item.status = "failed"

            if on_progress:
                on_progress(item)
            results.append(item)

        return results

    async def _process_parallel(
        self,
        items: list[BatchItem],
        processor: Callable,
        on_progress: Optional[Callable],
    ) -> list[BatchItem]:
        """完全并行处理"""
        async def process_item(item: BatchItem):
            item.status = "running"
            try:
                result = await processor(item.data)
                item.result = result
                item.status = "completed"
            except Exception as e:
                item.error = str(e)
                item.status = "failed"

            if on_progress:
                on_progress(item)

            return item

        tasks = [process_item(item) for item in items]
        return await asyncio.gather(*tasks)

    async def _process_limited(
        self,
        items: list[BatchItem],
        processor: Callable,
        on_progress: Optional[Callable],
    ) -> list[BatchItem]:
        """限制并发数处理 (Semaphore)"""
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def process_item(item: BatchItem):
            async with semaphore:
                item.status = "running"
                try:
                    result = await processor(item.data)
                    item.result = result
                    item.status = "completed"
                except Exception as e:
                    item.error = str(e)
                    item.status = "failed"

                if on_progress:
                    on_progress(item)

                return item

        tasks = [process_item(item) for item in items]
        return await asyncio.gather(*tasks)

    async def process_stream(
        self,
        items: list[Any],
        processor: Callable[[Any], Any],
    ) -> AsyncIterator[BatchItem]:
        """
        流式处理 - 逐个返回结果

        使用示例:
            async for item in processor.process_stream(data_list, process_func):
                print(f"Processed: {item.id}")
        """
        for item_data in items:
            item = BatchItem(id=str(uuid.uuid4()), data=item_data)
            item.status = "running"

            try:
                result = await processor(item_data)
                item.result = result
                item.status = "completed"
            except Exception as e:
                item.error = str(e)
                item.status = "failed"

            yield item


class RetryPolicy:
    """重试策略"""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        exponential_backoff: bool = True,
        max_delay: float = 60.0,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.exponential_backoff = exponential_backoff
        self.max_delay = max_delay

    async def execute(self, func: Callable, *args, **kwargs) -> Any:
        """执行带重试的函数"""
        last_error = None

        for attempt in range(self.max_retries + 1):
            try:
                if asyncio.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                else:
                    return func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    delay = self._calculate_delay(attempt)
                    logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
                    await asyncio.sleep(delay)

        raise last_error

    def _calculate_delay(self, attempt: int) -> float:
        """计算重试延迟"""
        if self.exponential_backoff:
            delay = self.base_delay * (2 ** attempt)
        else:
            delay = self.base_delay

        return min(delay, self.max_delay)


import uuid
