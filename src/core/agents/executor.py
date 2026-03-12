"""执行器 - 串行执行模式 (React Loop)"""

import asyncio
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class Executor:
    """串行执行器 - 使用 React Loop"""
    
    def __init__(self, agent, tool_registry):
        self.agent = agent
        self.tool_registry = tool_registry
    
    async def execute(self, execution_plan: dict, context: Any) -> dict:
        """执行任务 - 串行模式
        
        React Loop:
        1. 按顺序执行每个任务
        2. 检查结果
        3. 如果失败则修正
        4. 继续下一步
        
        Returns:
            执行结果
        """
        logger.info(f"[Executor] 开始串行执行...")
        
        task_graph = execution_plan.get("task_graph", [])
        results = []
        
        for i, task in enumerate(task_graph):
            task_id = task.get("task_id", i + 1)
            logger.info(f"[Executor] 执行任务 {task_id}: {task.get('description', '')[:30]}...")
            
            # 执行任务
            result = await self._execute_task(task, context)
            
            # 检查结果
            check = await self._check_result(result, task)
            
            if check.get("ok"):
                results.append(result)
            else:
                # 失败则尝试修正
                logger.warning(f"[Executor] 任务 {task_id} 结果不OK: {check.get('reason')}")
                # 修正后重试
                task = await self._revise_task(task, check)
                result = await self._execute_task(task, context)
                results.append(result)
        
        logger.info(f"[Executor] 串行执行完成，共 {len(results)} 个任务")
        
        return {
            "mode": "serial",
            "results": results
        }
    
    async def _execute_task(self, task: dict, context: Any) -> dict:
        """执行单个任务"""
        
        tool = task.get("tool", "")
        inputs = task.get("inputs", "")
        description = task.get("description", "")
        
        # 构建执行命令
        prompt = f"""执行任务: {description}

工具: {tool}
输入: {inputs}

请执行并返回结果。"""
        
        result = await self.agent.execute(prompt)
        
        return {
            "task_id": task.get("task_id"),
            "description": description,
            "result": result,
            "success": True
        }
    
    async def _check_result(self, result: dict, task: dict) -> dict:
        """检查任务执行结果"""
        
        if not result.get("success"):
            return {
                "ok": False,
                "reason": "任务执行失败"
            }
        
        # 可以添加更多检查逻辑
        # 比如检查返回内容是否为空等
        
        return {"ok": True}
    
    async def _revise_task(self, task: dict, check: dict) -> dict:
        """根据检查结果修正任务"""
        
        # 简单重试逻辑
        task["retry"] = task.get("retry", 0) + 1
        
        return task
