"""数据清洗工具"""

import json

from src.tools.base import Tool


class DataCleaner(Tool):
    """数据清洗"""

    name = "clean_data"
    description = "清洗数据，包括去重、填充缺失值、处理异常值等"
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
                "operations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "清洗操作: deduplicate, fill_missing, remove_outliers"
                }
            },
            "required": ["input_data"]
        }

    async def execute(self, input_data: str, operations: list = None, **kwargs) -> str:
        """执行数据清洗"""

        operations = operations or ["deduplicate"]

        try:
            if isinstance(input_data, str):
                data = json.loads(input_data)
            else:
                data = input_data
        except json.JSONDecodeError:
            return json.dumps({"error": "无效的 JSON 数据"})

        stats = {"original_count": len(data) if isinstance(data, list) else 0}

        for op in operations:
            if op == "deduplicate":
                data, op_stats = self._deduplicate(data)
                stats["deduplicated"] = op_stats
            elif op == "fill_missing":
                data = self._fill_missing(data)
                stats["filled_missing"] = True
            elif op == "remove_outliers":
                data, op_stats = self._remove_outliers(data)
                stats["outliers_removed"] = op_stats

        stats["final_count"] = len(data) if isinstance(data, list) else 0

        return json.dumps({"data": data, "stats": stats}, indent=2, ensure_ascii=False)

    def _deduplicate(self, data: list) -> tuple:
        """去重"""
        if not isinstance(data, list):
            return data, 0

        original_count = len(data)
        seen = set()
        deduplicated = []

        for item in data:
            # 简单基于字符串表示去重
            key = json.dumps(item, sort_keys=True, ensure_ascii=False)
            if key not in seen:
                seen.add(key)
                deduplicated.append(item)

        return deduplicated, original_count - len(deduplicated)

    def _fill_missing(self, data: list) -> list:
        """填充缺失值"""
        if not isinstance(data, list) or not data:
            return data

        # 如果是字典列表
        if isinstance(data[0], dict):
            # 计算每列的均值或最常见值
            for key in data[0].keys():
                values = [row.get(key) for row in data if row.get(key) is not None]
                if values:
                    # 使用最常见值或均值填充
                    if all(isinstance(v, (int, float)) for v in values):
                        fill_value = sum(values) / len(values)
                    else:
                        from collections import Counter
                        fill_value = Counter(values).most_common(1)[0][0]
                else:
                    fill_value = None

                # 填充
                for row in data:
                    if row.get(key) is None:
                        row[key] = fill_value

        return data

    def _remove_outliers(self, data: list) -> tuple:
        """移除异常值 (使用 IQR 方法)"""
        if not isinstance(data, list) or not data:
            return data, 0

        # 仅处理数值列
        if isinstance(data[0], dict):
            numeric_columns = []
            for key in data[0].keys():
                values = [row.get(key) for row in data if isinstance(row.get(key), (int, float))]
                if len(values) > 10:  # 至少有10个数值
                    numeric_columns.append(key)

            if not numeric_columns:
                return data, 0

            # 标记异常值
            outliers = set()
            for col in numeric_columns:
                values = sorted([row[col] for row in data if isinstance(row.get(col), (int, float))])
                if len(values) < 4:
                    continue

                q1 = values[len(values) // 4]
                q3 = values[3 * len(values) // 4]
                iqr = q3 - q1
                lower = q1 - 1.5 * iqr
                upper = q3 + 1.5 * iqr

                for row in data:
                    val = row.get(col)
                    if val is not None and (val < lower or val > upper):
                        outliers.add(id(row))

            # 移除
            original_count = len(data)
            data = [row for row in data if id(row) not in outliers]

            return data, original_count - len(data)

        return data, 0
