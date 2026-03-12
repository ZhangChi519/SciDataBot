"""主智能体 - 直接执行简单任务，判断是否需要并行"""

import re
import json
import logging
import os
from pathlib import Path
from typing import Optional, Any

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 5


class MainAgent:
    """主智能体
    
    职责:
    1. 直接执行简单任务（参考 nanobot 方式）
    2. 判断是否需要并行执行
    3. 如果需要并行，下发 给 TaskPlanner
    """
    
    def __init__(self, agent, tool_registry):
        self.agent = agent
        self.tool_registry = tool_registry
    
    async def execute(self, user_request: str, context: Any = None) -> dict:
        """执行任务
        
        流程:
        1. 分析任务类型
        2. 判断是否需要并行
        3. 如果不需要并行，直接执行并返回结果
        4. 如果需要并行，返回给 TaskPlanner
        
        Returns:
            {
                "need_parallel": True/False,
                "result": "直接执行的结果" (如果不需要并行),
                "task_spec": {} (如果需要并行)
            }
        """
        logger.info(f"[MainAgent] 开始处理: {user_request[:50]}...")
        
        # Step 1: 分析任务类型
        task_analysis = await self._analyze_task(user_request)
        
        # Step 2: 判断是否需要并行
        need_parallel = await self._check_need_parallel(task_analysis, user_request)
        
        if not need_parallel:
            # Step 3: 直接执行
            logger.info(f"[MainAgent] 任务类型: {task_analysis.get('task_type')}，直接执行")
            result = await self._direct_execute(user_request, context)
            return {
                "need_parallel": False,
                "result": result,
                "task_type": task_analysis.get("task_type")
            }
        else:
            # Step 4: 需要并行，返回任务规格
            logger.info(f"[MainAgent] 任务需要并行处理，下发给 TaskPlanner")
            task_spec = await self._create_task_spec(user_request, task_analysis)
            return {
                "need_parallel": True,
                "task_spec": task_spec,
                "task_type": task_analysis.get("task_type")
            }
    
    async def _analyze_task(self, user_request: str) -> dict:
        """分析任务类型"""
        
        prompt = f"""分析用户需求，判断任务类型。

用户请求: {user_request}

请输出JSON格式:
{{
    "task_type": "simple_query|data_prep|process|integration|general",
    "description": "任务简述",
    "data_path": "数据路径(如果有)",
    "simple_reason": "为什么判定为简单/复杂任务"
}}

判断逻辑:
- 天气查询、简单计算、文本生成等 → simple_query
- 多文件处理、数据解析等 → data_prep
- 数据处理、转换等 → process
- 需要多步骤整合 → integration
- 其他 → general

只输出JSON。"""

        result = await self.agent.execute(prompt)
        
        try:
            match = re.search(r'\{.*\}', result, re.DOTALL)
            if match:
                return json.loads(match.group())
        except:
            pass
        
        return {
            "task_type": "general",
            "description": user_request,
            "data_path": self._extract_path(user_request)
        }
    
    async def _check_need_parallel(self, task_analysis: dict, user_request: str) -> bool:
        """判断是否需要并行执行"""
        
        task_type = task_analysis.get("task_type", "general")
        
        # 简单查询类任务不需要并行
        if task_type in ["simple_query", "general"]:
            return False
        
        # 检查是否有多文件/多数据处理
        data_path = task_analysis.get("data_path", "")
        if data_path:
            path = Path(data_path)
            if path.exists() and path.is_dir():
                # 统计文件数量
                try:
                    files = list(path.iterdir())
                    if len(files) > 10:
                        # 多文件处理，需要并行
                        return True
                except:
                    pass
        
        # 检查关键词
        keywords = ["解析", "处理", "转换", "批量", "多个", "所有"]
        for kw in keywords:
            if kw in user_request:
                return True
        
        return False
    
    async def _direct_execute(self, user_request: str, context: Any = None) -> str:
        """直接执行任务（参考 nanobot 方式）"""
        
        # 使用 agent 直接执行
        result = await self.agent.execute(user_request)
        return result
    
    async def _create_task_spec(self, user_request: str, task_analysis: dict) -> dict:
        """创建任务规格，下发给 TaskPlanner"""
        
        return {
            "task_type": task_analysis.get("task_type", "data_prep"),
            "task_description": task_analysis.get("description", user_request),
            "data_path": task_analysis.get("data_path", ""),
            "user_request": user_request
        }
    
    def _extract_path(self, user_request: str) -> str:
        """从用户请求中提取数据路径"""
        match = re.search(r'(/[\w\u4e00-\u9fff_./-]+)', user_request)
        if match:
            return match.group(1)
        return ""


import os
