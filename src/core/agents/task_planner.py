"""任务规划智能体 - 判断执行策略、生成执行计划、迭代优化"""

import re
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 5


class TaskPlanner:
    """任务规划器 - 使用 React Loop 迭代优化"""
    
    def __init__(self, agent, tool_registry):
        self.agent = agent
        self.tool_registry = tool_registry
    
    async def plan(self, task_spec: dict) -> dict:
        """执行任务规划
        
        React Loop:
        1. 判断执行策略 (串行/并行)
        2. 生成执行计划
        3. 评估是否最优
        4. 如果不优则修正
        5. 重复直至OK或达到最大迭代
        
        Returns:
            ExecutionPlan (执行计划)
        """
        logger.info(f"[TaskPlanner] 开始规划任务...")
        
        execution_plan = await self._create_plan(task_spec)
        
        # 对于 data_prep 任务，直接使用并行模式，跳过迭代评估
        task_type = task_spec.get("task_type", "")
        if task_type == "data_prep":
            # 确保使用并行策略
            execution_plan["execution_strategy"] = "parallel"
            execution_plan["execution_mode"] = "processor_integrator"
            # 清除所有任务的依赖
            task_graph = execution_plan.get("task_graph", [])
            for task in task_graph:
                task["dependencies"] = []
            if task_graph:
                execution_plan["parallel_groups"] = [list(range(1, len(task_graph) + 1))]
            logger.info(f"[TaskPlanner] data_prep 任务直接使用并行模式")
            return execution_plan
        
        # 迭代评估优化 (用于其他类型任务)
        for iteration in range(MAX_ITERATIONS):
            logger.info(f"[TaskPlanner] 迭代 {iteration + 1}/{MAX_ITERATIONS}")
            
            # Step 1: 判断执行策略并生成执行计划
            execution_plan = await self._create_plan(task_spec)
            
            # Step 2: 评估是否最优
            evaluation = await self._evaluate_plan(execution_plan, task_spec)
            
            # Step 3: 如果OK，返回结果
            if evaluation.get("ok"):
                logger.info(f"[TaskPlanner] 迭代 {iteration + 1} 完成，计划评估通过")
                return execution_plan
            
            # Step 4: 如果不优，修正计划
            logger.warning(f"[TaskPlanner] 计划评估不通过: {evaluation.get('reason')}")
            execution_plan = await self._revise_plan(execution_plan, evaluation)
        
        # 达到最大迭代，返回当前结果
        logger.warning(f"[TaskPlanner] 达到最大迭代次数 {MAX_ITERATIONS}，返回当前计划")
        return execution_plan
    
    async def _create_plan(self, task_spec: dict) -> dict:
        """判断执行策略并生成执行计划"""
        
        task_type = task_spec.get("task_type", "general")
        task_description = task_spec.get("task_description", "")
        data_path = task_spec.get("data_path", "")
        
        prompt = f"""根据任务规格说明书，生成执行计划。

任务规格:
- 任务类型: {task_type}
- 任务描述: {task_description}
- 数据路径: {data_path}

请判断执行策略并输出JSON格式的执行计划:
{{
    "execution_strategy": "serial|parallel",
    "execution_mode": "react_loop|processor_integrator",
    "task_graph": [
        {{
            "task_id": 1,
            "description": "子任务描述",
            "tool": "使用的工具",
            "inputs": "输入",
            "outputs": "输出",
            "dependencies": []
        }}
    ],
    "parallel_groups": [[1,2,3], [4,5,6]],  // 如果并行，指定哪些任务可以并行
    "result_handling": {{
        "mode": "context|file|return",
        "save_format": "json|markdown|csv",
        "result_path": "结果保存路径"
    }}
}}

判断逻辑:
- 如果是多文件/多目录处理 → 并行 (processor_integrator)
- 如果有步骤依赖 → 串行 (react_loop)
- 其他 → 串行 (react_loop) (默认)

只输出JSON，不要其他内容。"""

        result = await self.agent.execute(prompt)
        
        # 解析JSON
        try:
            match = re.search(r'\{.*\}', result, re.DOTALL)
            if match:
                plan = json.loads(match.group())
                return plan
        except json.JSONDecodeError:
            pass
        
        # 解析失败，返回默认计划
        return self._create_default_plan(task_spec)
    
    def _create_default_plan(self, task_spec: dict) -> dict:
        """创建默认执行计划"""
        
        data_path = task_spec.get("data_path", "")
        
        return {
            "execution_strategy": "serial",
            "execution_mode": "react_loop",
            "task_graph": [
                {
                    "task_id": 1,
                    "description": task_spec.get("task_description", ""),
                    "tool": "list_dir",
                    "inputs": data_path,
                    "outputs": "",
                    "dependencies": []
                }
            ],
            "parallel_groups": [],
            "result_handling": {
                "mode": "context",
                "save_format": "markdown",
                "result_path": ""
            }
        }
    
    async def _evaluate_plan(self, execution_plan: dict, task_spec: dict) -> dict:
        """评估执行计划是否最优"""
        
        strategy = execution_plan.get("execution_strategy", "serial")
        task_graph = execution_plan.get("task_graph", [])
        
        # 检查是否有多个可并行的任务
        if len(task_graph) > 1 and strategy == "serial":
            # 建议改为并行
            return {
                "ok": False,
                "reason": f"有 {len(task_graph)} 个任务，建议改为并行执行",
                "suggestion": "parallel"
            }
        
        # 检查任务是否有依赖
        has_dependencies = False
        for task in task_graph:
            if task.get("dependencies"):
                has_dependencies = True
                break
        
        if has_dependencies and strategy == "parallel":
            return {
                "ok": False,
                "reason": "任务有依赖关系，不适合并行",
                "suggestion": "serial"
            }
        
        return {"ok": True}
    
    async def _revise_plan(self, execution_plan: dict, evaluation: dict) -> dict:
        """根据评估结果修正执行计划"""
        
        suggestion = evaluation.get("suggestion", "")
        
        if suggestion == "parallel":
            execution_plan["execution_strategy"] = "parallel"
            execution_plan["execution_mode"] = "processor_integrator"
            # 尝试分组
            task_graph = execution_plan.get("task_graph", [])
            if task_graph:
                # 清除依赖，全部并行
                for task in task_graph:
                    task["dependencies"] = []
                # 所有任务放一组并行
                execution_plan["parallel_groups"] = [list(range(1, len(task_graph) + 1))]
        
        elif suggestion == "serial":
            execution_plan["execution_strategy"] = "serial"
            execution_plan["execution_mode"] = "react_loop"
            execution_plan["parallel_groups"] = []
            # 清除依赖
            task_graph = execution_plan.get("task_graph", [])
            for task in task_graph:
                task["dependencies"] = []
        
        return execution_plan
