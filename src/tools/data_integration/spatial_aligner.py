"""空间对齐工具"""

import json

from src.tools.base import Tool


class SpatialAligner(Tool):
    """空间对齐"""

    name = "align_spatial"
    description = "将多个数据集按空间维度对齐"
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
                "lat_column": {
                    "type": "string",
                    "description": "纬度列名"
                },
                "lon_column": {
                    "type": "string",
                    "description": "经度列名"
                },
                "resolution": {
                    "type": "number",
                    "description": "空间分辨率（度）"
                }
            },
            "required": ["datasets", "lat_column", "lon_column"]
        }

    async def execute(self, datasets: str, lat_column: str, lon_column: str,
                     resolution: float = 0.1, **kwargs) -> str:
        """执行空间对齐"""

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
        aligned = self._align_spatial(data_list, lat_column, lon_column, resolution)

        return json.dumps(aligned, indent=2, ensure_ascii=False)

    def _align_spatial(self, data_list: list, lat_col: str, lon_col: str, resolution: float) -> dict:
        """空间对齐"""

        # 创建空间桶
        space_buckets = {}

        for i, data in enumerate(data_list):
            if not isinstance(data, list):
                continue

            for row in data:
                if isinstance(row, dict) and lat_col in row and lon_col in row:
                    lat = float(row[lat_col])
                    lon = float(row[lon_col])

                    # 桶键
                    bucket_lat = round(lat / resolution) * resolution
                    bucket_lon = round(lon / resolution) * resolution
                    key = (bucket_lat, bucket_lon)

                    if key not in space_buckets:
                        space_buckets[key] = {}

                    space_buckets[key][f"dataset_{i}"] = row

        # 构建结果
        result = {
            "aligned": True,
            "resolution": resolution,
            "spatial_buckets": len(space_buckets),
            "data": []
        }

        for (lat, lon), rows in sorted(space_buckets.items()):
            merged = {"lat": lat, "lon": lon}
            merged.update(rows)
            result["data"].append(merged)

        return result
