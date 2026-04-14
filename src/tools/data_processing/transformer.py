"""数据转换工具"""

import json

from src.tools.base import Tool


class DataTransformer(Tool):
    """数据转换"""

    name = "transform_data"
    description = "转换数据格式和结构"
    category = "data_processing"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "input_data": {
                    "type": "string",
                    "description": "输入数据 (JSON 字符串)"
                },
                "transform_type": {
                    "type": "string",
                    "enum": ["pivot", "melt", "aggregate", "map", "filter"],
                    "description": "转换类型"
                },
                "params": {
                    "type": "object",
                    "description": "转换参数"
                }
            },
            "required": ["input_data", "transform_type"]
        }

    async def execute(self, input_data: str, transform_type: str, params: dict = None, **kwargs) -> str:
        """执行数据转换"""

        params = params or {}

        # 解析输入数据
        try:
            if isinstance(input_data, str):
                data = json.loads(input_data)
            else:
                data = input_data
        except json.JSONDecodeError:
            return json.dumps({"error": "无效的 JSON 数据"})

        if transform_type == "map":
            result = self._transform_map(data, params)
        elif transform_type == "filter":
            result = self._transform_filter(data, params)
        elif transform_type == "aggregate":
            result = self._transform_aggregate(data, params)
        else:
            return json.dumps({"error": f"不支持的转换类型: {transform_type}"})

        return json.dumps(result, indent=2, ensure_ascii=False)

    def _transform_map(self, data: list, params: dict) -> dict:
        """映射转换"""
        column = params.get("column")
        mapping = params.get("mapping", {})

        if not isinstance(data, list) or not data:
            return {"error": "数据必须是数组"}

        if isinstance(data[0], dict) and column:
            # 列映射
            for row in data:
                if column in row:
                    row[column] = mapping.get(row[column], row[column])
        elif isinstance(data[0], list):
            # 索引映射
            col_idx = params.get("column_index", 0)
            for row in data:
                if col_idx < len(row):
                    row[col_idx] = mapping.get(row[col_idx], row[col_idx])

        return {"data": data, "transformed": True}

    def _transform_filter(self, data: list, params: dict) -> dict:
        """过滤转换"""
        condition = params.get("condition", "")
        column = params.get("column")

        if not isinstance(data, list) or not data:
            return {"error": "数据必须是数组"}

        filtered = []

        for row in data:
            if isinstance(row, dict) and column:
                # 字典条件
                value = row.get(column)
                if self._evaluate_condition(value, condition):
                    filtered.append(row)
            elif isinstance(row, list):
                # 列表条件
                col_idx = params.get("column_index", 0)
                if col_idx < len(row):
                    value = row[col_idx]
                    if self._evaluate_condition(value, condition):
                        filtered.append(row)

        return {"data": filtered, "original_count": len(data), "filtered_count": len(filtered)}

    def _transform_aggregate(self, data: list, params: dict) -> dict:
        """聚合转换"""
        group_by = params.get("group_by")
        agg_column = params.get("agg_column")
        agg_func = params.get("agg_func", "sum")

        if not isinstance(data, list) or not data:
            return {"error": "数据必须是数组"}

        from collections import defaultdict

        groups = defaultdict(list)

        for row in data:
            if isinstance(row, dict) and group_by in row:
                key = row[group_by]
                if agg_column and agg_column in row:
                    groups[key].append(row[agg_column])

        result = {}
        for key, values in groups.items():
            if agg_func == "sum":
                result[key] = sum(values)
            elif agg_func == "avg":
                result[key] = sum(values) / len(values) if values else 0
            elif agg_func == "count":
                result[key] = len(values)
            elif agg_func == "min":
                result[key] = min(values) if values else None
            elif agg_func == "max":
                result[key] = max(values) if values else None

        return {"data": result, "group_by": group_by, "agg": agg_func}

    def _evaluate_condition(self, value, condition: str) -> bool:
        """评估条件"""
        if not condition:
            return True

        # 简化实现：支持基本比较
        if condition.startswith("=="):
            return value == condition[2:].strip()
        elif condition.startswith("!="):
            return value != condition[2:].strip()
        elif condition.startswith(">"):
            return value > condition[1:].strip()
        elif condition.startswith("<"):
            return value < condition[1:].strip()

        return True
