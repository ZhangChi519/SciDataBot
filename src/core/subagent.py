"""SubAgent管理 - 借鉴NanoBot"""
import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List, Callable
from pathlib import Path
from datetime import datetime

from loguru import logger


@dataclass
class SubAgentTask:
    """子Agent任务"""
    task_id: str
    agent_name: str
    input_data: str
    status: str = "pending"  # pending, running, completed, failed, cancelled
    result: Optional[str] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())
    completed_at: Optional[float] = None
    session_key: Optional[str] = None


class SubAgentManager:
    """子Agent管理器 - 支持创建、取消、查询子Agent任务"""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self._tasks: Dict[str, SubAgentTask] = {}
        self._active_tasks: Dict[str, List[asyncio.Task]] = {}
        self._lock = asyncio.Lock()

    async def create_task(
        self,
        agent_name: str,
        input_data: str,
        session_key: Optional[str] = None,
    ) -> str:
        """创建子Agent任务"""
        async with self._lock:
            task_id = f"subagent-{uuid.uuid4().hex[:8]}"
            task = SubAgentTask(
                task_id=task_id,
                agent_name=agent_name,
                input_data=input_data,
                session_key=session_key,
            )
            self._tasks[task_id] = task
            logger.info(f"Created subagent task: {task_id} for {agent_name}")
            return task_id

    async def run_task(
        self,
        task_id: str,
        agent_factory: Callable,
        on_progress: Optional[Callable[[str, bool], None]] = None,
    ) -> str:
        """运行子Agent任务"""
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        task.status = "running"
        
        try:
            # 创建Agent实例
            agent = agent_factory(task.agent_name)
            
            # 执行任务
            logger.info(f"Running subagent task: {task_id}")
            result = await agent.execute(
                task.input_data,
                on_progress=on_progress,
            )
            
            task.result = result
            task.status = "completed"
            task.completed_at = datetime.now().timestamp()
            logger.info(f"Subagent task completed: {task_id}")
            return result
            
        except asyncio.CancelledError:
            task.status = "cancelled"
            task.error = "Task cancelled"
            raise
        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            logger.error(f"Subagent task failed: {task_id} - {e}")
            raise

    async def cancel_task(self, task_id: str) -> bool:
        """取消子Agent任务"""
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            
            if task.status == "running":
                # 取消正在运行的任务
                if task_id in self._active_tasks:
                    for t in self._active_tasks[task_id]:
                        if not t.done():
                            t.cancel()
                task.status = "cancelled"
                task.error = "Cancelled by user"
                return True
            elif task.status == "pending":
                task.status = "cancelled"
                return True
            
            return False

    async def cancel_by_session(self, session_key: str) -> int:
        """取消指定会话的所有任务"""
        cancelled = 0
        async with self._lock:
            for task in self._tasks.values():
                if task.session_key == session_key and task.status == "running":
                    await self.cancel_task(task.task_id)
                    cancelled += 1
        return cancelled

    def get_task(self, task_id: str) -> Optional[SubAgentTask]:
        """获取任务状态"""
        return self._tasks.get(task_id)

    def get_tasks_by_session(self, session_key: str) -> List[SubAgentTask]:
        """获取指定会话的所有任务"""
        return [
            t for t in self._tasks.values()
            if t.session_key == session_key
        ]

    def get_active_tasks(self, session_key: Optional[str] = None) -> List[SubAgentTask]:
        """获取活跃任务"""
        if session_key:
            return [
                t for t in self._tasks.values()
                if t.status == "running" and t.session_key == session_key
            ]
        return [t for t in self._tasks.values() if t.status == "running"]

    async def cleanup_completed(self, older_than_seconds: int = 3600) -> int:
        """清理已完成的任务"""
        now = datetime.now().timestamp()
        cleaned = 0
        
        async with self._lock:
            to_remove = []
            for task_id, task in self._tasks.items():
                if task.status in ("completed", "failed", "cancelled"):
                    if task.completed_at and (now - task.completed_at) > older_than_seconds:
                        to_remove.append(task_id)
            
            for task_id in to_remove:
                del self._tasks[task_id]
                cleaned += 1
        
        return cleaned

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = {
            "total": len(self._tasks),
            "pending": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0,
        }
        
        for task in self._tasks.values():
            stats[task.status] = stats.get(task.status, 0) + 1
        
        return stats
