"""时间对齐工具"""

import json
from datetime import datetime

from src.tools.base import Tool


class TemporalAligner(Tool):
    """时间对齐"""

    name = "align_temporal"
    description = "将多个数据集按时间维度对齐"
    category = "data_integration"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "datasets": {
                    "type": "string",
                    "description": "数据集列表 (JSON 字符串)"
                },
                "time_column": {
                    "type": "string",
                    "description": "时间列名"
                },
                "interval": {
                    "type": "string",
                    "description": "对齐间隔: hourly, daily, monthly"
                }
            },
            "required": ["datasets", "time_column"]
        }

    async def execute(self, datasets: str, time_column: str, interval: str = "daily", **kwargs) -> str:
        """执行时间对齐"""

        try:
            if isinstance(datasets, str):
                data_list = json.loads(datasets)
            else:
                data_list = datasets
        except json.JSONDecodeError:
            return json.dumps({"error": "无效的 JSON 数据"})

        if not isinstance(data_list, list) or len(data_list) < 2:
            return json.dumps({"error": "需要至少两个数据集"})

        # 对齐
        aligned = self._align_datasets(data_list, time_column, interval)

        return json.dumps(aligned, indent=2, ensure_ascii=False)

    def _align_datasets(self, data_list: list, time_column: str, interval: str) -> dict:
        """对齐数据集"""

        # 收集所有时间点
        all_times = set()
        for data in data_list:
            if isinstance(data, list):
                for row in data:
                    if isinstance(row, dict) and time_column in row:
                        all_times.add(self._parse_time(row[time_column]))

        # 按间隔分组
        time_buckets = {}
        for t in sorted(all_times):
            bucket = self._get_time_bucket(t, interval)
            if bucket not in time_buckets:
                time_buckets[bucket] = []
            time_buckets[bucket].append(t)

        # 合并
        result = {
            "aligned": True,
            "interval": interval,
            "time_buckets": len(time_buckets),
            "data": []
        }

        # 为每个时间桶创建合并记录
        for bucket, times in sorted(time_buckets.items()):
            merged = {"time": bucket}
            for i, data in enumerate(data_list):
                # 找到该时间桶内最接近的时间点
                value = self._find_closest_value(data, times, time_column)
                merged[f"dataset_{i}"] = value

            result["data"].append(merged)

        return result

    def _parse_time(self, time_str) -> datetime:
        """解析时间"""
        if isinstance(time_str, datetime):
            return time_str

        # 尝试多种格式
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%Y-%m-%dT%H:%M:%S",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(str(time_str), fmt)
            except ValueError:
                continue

        return datetime.now()

    def _get_time_bucket(self, dt: datetime, interval: str) -> str:
        """获取时间桶"""
        if interval == "hourly":
            return dt.strftime("%Y-%m-%d %H:00")
        elif interval == "daily":
            return dt.strftime("%Y-%m-%d")
        elif interval == "monthly":
            return dt.strftime("%Y-%m")
        else:
            return dt.strftime("%Y-%m-%d")

    def _find_closest_value(self, data: list, target_times: list, time_column: str):
        """找到最接近的值"""
        if not isinstance(data, list) or not data:
            return None

        for target in target_times:
            for row in data:
                if isinstance(row, dict) and time_column in row:
                    row_time = self._parse_time(row[time_column])
                    if abs((row_time - target).total_seconds()) < 3600:  # 1小时内
                        return row

        return None
