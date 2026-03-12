"""意图解析智能体 - 分析任务类型、环境检查、迭代优化"""

import re
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 5


class IntentParser:
    """意图解析器 - 使用 React Loop 迭代优化"""
    
    def __init__(self, agent, tool_registry):
        self.agent = agent
        self.tool_registry = tool_registry
    
    async def parse(self, user_request: str) -> dict:
        """执行意图解析
        
        React Loop:
        1. 分析任务类型
        2. 检查环境
        3. 如果不OK则修正
        4. 重复直至OK或达到最大迭代
        
        Returns:
            TaskSpec (任务规格说明书)
        """
        logger.info(f"[IntentParser] 开始解析: {user_request[:50]}...")
        
        # 迭代优化
        for iteration in range(MAX_ITERATIONS):
            logger.info(f"[IntentParser] 迭代 {iteration + 1}/{MAX_ITERATIONS}")
            
            # Step 1: 分析任务类型，形成任务描述
            task_spec = await self._analyze_task(user_request)
            
            # Step 2: 检查任务环境
            env_check = await self._check_environment(task_spec)
            
            # Step 3: 评估是否OK
            if env_check.get("ok"):
                logger.info(f"[IntentParser] 迭代 {iteration + 1} 完成，环境检查通过")
                return task_spec
            
            # Step 4: 如果不OK，修正任务描述
            logger.warning(f"[IntentParser] 环境检查不通过: {env_check.get('reason')}")
            task_spec = await self._revise_task(task_spec, env_check)
        
        # 达到最大迭代，返回当前结果
        logger.warning(f"[IntentParser] 达到最大迭代次数 {MAX_ITERATIONS}，返回当前结果")
        return task_spec
    
    async def _analyze_task(self, user_request: str) -> dict:
        """分析任务类型，形成详细任务描述"""
        
        prompt = f"""分析用户需求，形成任务规格说明书。

用户请求: {user_request}

请输出JSON格式的分析结果:
{{
    "task_type": "data_prep|query|process|integration|general",
    "task_description": "详细任务描述",
    "task_goals": ["目标1", "目标2"],
    "data_path": "数据路径(如果有)",
    "output_format": "期望输出格式",
    "constraints": ["约束条件1", "约束条件2"]
}}

只输出JSON，不要其他内容。"""

        result = await self.agent.execute(prompt)
        
        # 解析JSON
        try:
            match = re.search(r'\{.*\}', result, re.DOTALL)
            if match:
                spec = json.loads(match.group())
                return spec
        except json.JSONDecodeError:
            pass
        
        # 解析失败，返回默认规格
        return {
            "task_type": "general",
            "task_description": user_request,
            "task_goals": [],
            "data_path": self._extract_path(user_request),
            "output_format": "auto",
            "constraints": []
        }
    
    async def _check_environment(self, task_spec: dict) -> dict:
        """检查任务环境"""
        
        data_path = task_spec.get("data_path", "")
        
        # 如果没有数据路径，返回OK
        if not data_path:
            return {"ok": True}
        
        # 检查路径是否存在
        path = Path(data_path)
        if not path.exists():
            return {
                "ok": False,
                "reason": f"路径不存在: {data_path}",
                "action": "修正数据路径"
            }
        
        # 检查权限
        if not os.access(path, os.R_OK):
            return {
                "ok": False,
                "reason": f"路径不可读: {data_path}",
                "action": "检查权限"
            }
        
        return {"ok": True}
    
    async def _revise_task(self, task_spec: dict, env_check: dict) -> dict:
        """根据环境检查结果修正任务规格"""
        
        reason = env_check.get("reason", "")
        
        # 如果路径不存在，尝试推断正确路径
        data_path = task_spec.get("data_path", "")
        
        # 尝试常见的父目录
        if data_path:
            parent = str(Path(data_path).parent)
            if Path(parent).exists():
                task_spec["data_path"] = parent
                task_spec["note"] = f"自动修正路径: {data_path} -> {parent}"
        
        return task_spec
    
    def _extract_path(self, user_request: str) -> str:
        """从用户请求中提取数据路径"""
        match = re.search(r'(/[\w\u4e00-\u9fff_./-]+)', user_request)
        if match:
            return match.group(1)
        return ""


import os
