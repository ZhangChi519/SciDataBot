"""并行处理器 - 并行执行模式"""

import asyncio
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class Processor:
    """并行处理器 - 同时执行多个任务"""
    
    def __init__(self, agent, tool_registry, lane_scheduler):
        self.agent = agent
        self.tool_registry = tool_registry
        self.lane_scheduler = lane_scheduler
    
    async def execute(self, execution_plan: dict, context: Any) -> dict:
        """执行任务 - 并行模式
        
        并行执行 task_graph 中的任务
        执行完成后交给 Integrator 整合结果
        
        Returns:
            并行执行结果
        """
        logger.info(f"[Processor] 开始并行执行...")
        
        task_graph = execution_plan.get("task_graph", [])
        parallel_groups = execution_plan.get("parallel_groups", [])
        
        all_results = []
        
        # 如果有分组，按组并行执行
        if parallel_groups:
            for group in parallel_groups:
                group_tasks = [task for task in task_graph if task.get("task_id") in group]
                logger.info(f"[Processor] 并行执行组: {group}")
                group_results = await self._execute_group(group_tasks, context)
                all_results.extend(group_results)
        else:
            # 没有分组，所有任务并行
            logger.info(f"[Processor] 并行执行所有 {len(task_graph)} 个任务")
            all_results = await self._execute_group(task_graph, context)
        
        logger.info(f"[Processor] 并行执行完成，共 {len(all_results)} 个任务")
        
        return {
            "mode": "parallel",
            "results": all_results
        }
    
    async def _execute_group(self, tasks: List[dict], context: Any) -> List[dict]:
        """并行执行一组任务"""
        
        # 创建任务列表
        task_coroutines = [self._execute_task(task, context) for task in tasks]
        
        # 并行执行
        results = await asyncio.gather(*task_coroutines, return_exceptions=True)
        
        # 处理结果
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"[Processor] 任务 {i} 执行出错: {result}")
                processed_results.append({
                    "task_id": tasks[i].get("task_id"),
                    "success": False,
                    "error": str(result)
                })
            else:
                processed_results.append(result)
        
        return processed_results
    
    async def _execute_task(self, task: dict, context: Any) -> dict:
        """执行单个任务"""
        
        tool = task.get("tool", "")
        inputs = task.get("inputs", "")
        outputs = task.get("outputs", "")
        description = task.get("description", "")
        task_id = task.get("task_id", 0)
        
        logger.info(f"[Processor] 执行任务 {task_id}: {description[:30]}...")
        
        prompt = f"""执行数据处理任务:

任务: {description}
工具: {tool}
输入: {inputs}
输出: {outputs}

请:
1. 使用 {tool} 工具处理任务
2. 根据任务类型执行相应操作
3. 返回处理结果

任务类型判断:
- 如果是文件/目录列表 → 遍历处理每个文件
- 如果是单文件 → 直接处理
- 如果是查询 → 返回查询结果
- 如果是数据处理 → 执行转换/提取等操作

返回格式:
{{
    "success": true/false,
    "processed_count": 处理的文件数,
    "results": [...],
    "errors": [...]
}}

如果处理成功，返回实际的处理结果。如果失败，说明错误原因。"""
        
        async def task_fn():
            return await self.agent.execute(prompt)
        
        try:
            result = await self.lane_scheduler.submit_task("subagent", task_fn)
        except asyncio.TimeoutError:
            logger.warning(f"[Processor] 任务 {task_id} 执行超时")
            return {
                "task_id": task_id,
                "description": description,
                "success": False,
                "error": "任务执行超时"
            }
        except Exception as e:
            logger.error(f"[Processor] 任务 {task_id} 执行失败: {e}")
            return {
                "task_id": task_id,
                "description": description,
                "success": False,
                "error": str(e)
            }
        
        return {
            "task_id": task_id,
            "description": description,
            "result": result,
            "success": True
        }
