"""统计分析工具"""

import json
from collections import Counter

from src.tools.base import Tool


class StatisticsAnalyzer(Tool):
    """统计分析"""

    name = "analyze_statistics"
    description = "对数据进行统计分析"
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
                "column": {
                    "type": "string",
                    "description": "要分析的列（可选）"
                }
            },
            "required": ["input_data"]
        }

    async def execute(self, input_data: str, column: str = None, **kwargs) -> str:
        """执行统计分析"""

        try:
            if isinstance(input_data, str):
                data = json.loads(input_data)
            else:
                data = input_data
        except json.JSONDecodeError:
            return json.dumps({"error": "无效的 JSON 数据"})

        if not isinstance(data, list) or not data:
            return json.dumps({"error": "数据必须是数组"})

        # 分析
        if isinstance(data[0], dict):
            result = self._analyze_dict_list(data, column)
        elif isinstance(data[0], list):
            result = self._analyze_list_list(data, column)
        else:
            result = self._analyze_primitive_list(data)

        return json.dumps(result, indent=2, ensure_ascii=False)

    def _analyze_dict_list(self, data: list, column: str = None) -> dict:
        """分析字典列表"""
        result = {"type": "dict_list", "row_count": len(data)}

        # 确定要分析的列
        if column:
            columns = [column]
        else:
            columns = list(data[0].keys()) if data else []

        result["columns"] = {}

        for col in columns:
            values = [row.get(col) for row in data if row.get(col) is not None]

            if not values:
                continue

            # 数值列
            numeric_values = [v for v in values if isinstance(v, (int, float))]
            if len(numeric_values) > len(values) * 0.5:  # 超过一半是数值
                result["columns"][col] = self._calculate_numeric_stats(numeric_values)
            else:
                result["columns"][col] = self._calculate_categorical_stats(values)

        return result

    def _analyze_list_list(self, data: list, column: int = None) -> dict:
        """分析列表列表"""
        result = {"type": "list_list", "row_count": len(data)}

        if column is not None:
            values = [row[column] for row in data if column < len(row)]
            if values and isinstance(values[0], (int, float)):
                return self._calculate_numeric_stats(values)
            return self._calculate_categorical_stats(values)

        return result

    def _analyze_primitive_list(self, data: list) -> dict:
        """分析原始列表"""
        if data and isinstance(data[0], (int, float)):
            return self._calculate_numeric_stats(data)
        return self._calculate_categorical_stats(data)

    def _calculate_numeric_stats(self, values: list) -> dict:
        """计算数值统计"""
        values = sorted(values)
        n = len(values)

        stats = {
            "type": "numeric",
            "count": n,
            "min": min(values),
            "max": max(values),
            "mean": sum(values) / n,
        }

        # 中位数
        if n % 2 == 0:
            stats["median"] = (values[n // 2 - 1] + values[n // 2]) / 2
        else:
            stats["median"] = values[n // 2]

        # 标准差
        mean = stats["mean"]
        variance = sum((x - mean) ** 2 for x in values) / n
        stats["std"] = variance ** 0.5

        # 分位数
        stats["q1"] = values[n // 4]
        stats["q3"] = values[3 * n // 4]

        return stats

    def _calculate_categorical_stats(self, values: list) -> dict:
        """计算分类统计"""
        counter = Counter(values)
        total = len(values)

        stats = {
            "type": "categorical",
            "count": total,
            "unique": len(counter),
            "top_values": [
                {"value": v, "count": c, "ratio": round(c / total, 3)}
                for v, c in counter.most_common(10)
            ]
        }

        return stats
