"""规划生成工具"""

import json

from src.tools.base import Tool


class PlanningGenerator(Tool):
    """生成处理规划"""

    name = "generate_plan"
    description = "根据意图生成数据处理规划"
    category = "intent_parser"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "description": "识别的意图 (JSON 格式)"
                },
                "query": {
                    "type": "string",
                    "description": "原始查询"
                }
            },
            "required": ["intent", "query"]
        }

    async def execute(self, intent: str, query: str, **kwargs) -> str:
        """生成处理规划"""

        # 解析意图
        try:
            if isinstance(intent, str):
                intent_data = json.loads(intent)
            else:
                intent_data = intent
        except json.JSONDecodeError:
            intent_data = {"intent_type": "query", "domain": "general"}

        intent_type = intent_data.get("intent_type", "query")
        domain = intent_data.get("domain", "general")

        # 根据意图生成规划
        plan = self._generate_plan_for_intent(intent_type, domain, query)

        return json.dumps(plan, indent=2, ensure_ascii=False)

    def _generate_plan_for_intent(self, intent_type: str, domain: str, query: str) -> dict:
        """根据意图类型生成规划"""

        plan = {
            "intent_type": intent_type,
            "domain": domain,
            "phases": [],
        }

        if intent_type == "analysis":
            plan["phases"] = [
                {"phase": 1, "name": "数据接入", "lane": "data_access", "tasks": ["检测格式", "提取元数据"]},
                {"phase": 2, "name": "数据处理", "lane": "processing", "tasks": ["数据清洗", "统计分析"]},
                {"phase": 3, "name": "结果输出", "lane": "integration", "tasks": ["生成报告"]},
            ]
        elif intent_type == "processing":
            plan["phases"] = [
                {"phase": 1, "name": "数据接入", "lane": "data_access", "tasks": ["检测格式"]},
                {"phase": 2, "name": "数据处理", "lane": "processing", "tasks": ["数据转换", "数据清洗", "格式转换"]},
                {"phase": 3, "name": "保存结果", "lane": "integration", "tasks": ["导出数据"]},
            ]
        elif intent_type == "integration":
            plan["phases"] = [
                {"phase": 1, "name": "多源接入", "lane": "data_access", "tasks": ["接入数据源1", "接入数据源2"]},
                {"phase": 2, "name": "数据对齐", "lane": "integration", "tasks": ["时间对齐", "空间对齐", "实体匹配"]},
                {"phase": 3, "name": "整合输出", "lane": "integration", "tasks": ["数据融合", "导出"]},
            ]
        elif intent_type == "comparison":
            plan["phases"] = [
                {"phase": 1, "name": "多源接入", "lane": "data_access", "tasks": ["接入数据A", "接入数据B"]},
                {"phase": 2, "name": "对比分析", "lane": "processing", "tasks": ["数据清洗", "统计对比"]},
                {"phase": 3, "name": "结果输出", "lane": "integration", "tasks": ["生成对比报告"]},
            ]
        else:
            plan["phases"] = [
                {"phase": 1, "name": "数据接入", "lane": "data_access", "tasks": ["检测格式"]},
                {"phase": 2, "name": "处理", "lane": "processing", "tasks": ["处理数据"]},
                {"phase": 3, "name": "输出", "lane": "integration", "tasks": ["返回结果"]},
            ]

        return plan
