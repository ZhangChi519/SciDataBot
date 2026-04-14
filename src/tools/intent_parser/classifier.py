"""意图分类工具"""

import json

from src.tools.base import Tool


class IntentClassifier(Tool):
    """意图分类"""

    name = "classify_intent"
    description = "分析用户需求，识别意图类型和领域"
    category = "intent_parser"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "用户查询"
                }
            },
            "required": ["query"]
        }

    async def execute(self, query: str, **kwargs) -> str:
        """执行意图分类"""

        # 意图类型
        intent_types = [
            "analysis",  # 数据分析
            "processing",  # 数据处理
            "integration",  # 数据整合
            "retrieval",  # 数据检索
            "comparison",  # 对比分析
            "visualization",  # 可视化
            "prediction",  # 预测
            "query",  # 问答查询
        ]

        # 领域
        domains = [
            "environmental",  # 环境科学
            "astronomy",  # 天文学
            "geology",  # 地质学
            "biology",  # 生物学
            "physics",  # 物理学
            "chemistry",  # 化学
            "climate",  # 气候
            "general",  # 通用
        ]

        # 简化实现：基于关键词匹配
        query_lower = query.lower()

        intent = "query"
        if any(k in query_lower for k in ["分析", "analyze", "analysis"]):
            intent = "analysis"
        elif any(k in query_lower for k in ["处理", "process", "清洗", "clean"]):
            intent = "processing"
        elif any(k in query_lower for k in ["整合", "integrate", "合并", "merge"]):
            intent = "integration"
        elif any(k in query_lower for k in ["检索", "搜索", "search", "find"]):
            intent = "retrieval"
        elif any(k in query_lower for k in ["比较", "对比", "compare"]):
            intent = "comparison"
        elif any(k in query_lower for k in ["可视化", "visualize", "绘图", "chart"]):
            intent = "visualization"

        domain = "general"
        if any(k in query_lower for k in ["pm2.5", "空气质量", "air quality", "污染"]):
            domain = "environmental"
        elif any(k in query_lower for k in ["天文", "星", "planet", "star"]):
            domain = "astronomy"
        elif any(k in query_lower for k in ["气候", "温度", "weather", "climate"]):
            domain = "climate"

        result = {
            "intent_type": intent,
            "domain": domain,
            "confidence": 0.85,
            "keywords": self._extract_keywords(query),
        }

        return json.dumps(result, indent=2, ensure_ascii=False)

    def _extract_keywords(self, query: str) -> list:
        """提取关键词"""
        # 简化实现
        words = query.replace(",", " ").replace(".", " ").split()
        return [w for w in words if len(w) > 2]
