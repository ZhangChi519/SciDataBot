"""元数据提取工具"""

import json
from pathlib import Path

from src.tools.base import Tool


class MetadataExtractor(Tool):
    """提取元数据"""

    name = "extract_metadata"
    description = "从数据文件中提取元数据信息"
    category = "data_access"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "数据文件路径"
                },
                "deep": {
                    "type": "boolean",
                    "description": "是否深度提取（可能较慢）",
                    "default": False
                }
            },
            "required": ["file_path"]
        }

    async def execute(self, file_path: str, deep: bool = False, **kwargs) -> str:
        """执行元数据提取"""

        path = Path(file_path)

        if not path.exists():
            return json.dumps({"error": f"文件不存在: {file_path}"})

        suffix = path.suffix.lower()

        # 根据格式选择提取方法
        if suffix == '.csv':
            return await self._extract_csv_metadata(path, deep)
        elif suffix == '.json':
            return await self._extract_json_metadata(path)
        elif suffix == '.fits':
            return await self._extract_fits_metadata(path)
        elif suffix == '.nc':
            return await self._extract_netcdf_metadata(path)
        else:
            return await self._extract_generic_metadata(path)

    async def _extract_csv_metadata(self, path: Path, deep: bool) -> str:
        """提取 CSV 元数据"""
        import csv

        metadata = {
            "format": "CSV",
            "file": path.name,
            "columns": [],
        }

        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                # 读取第一行作为列名
                reader = csv.reader(f)
                headers = next(reader)
                metadata["column_count"] = len(headers)
                metadata["columns"] = headers

                if deep:
                    # 深度分析：读取更多行分析类型
                    sample = []
                    for i, row in enumerate(reader):
                        if i >= 100:
                            break
                        sample.append(row)

                    # 分析每列的类型
                    for i, col in enumerate(headers):
                        col_values = [row[i] for row in sample if i < len(row)]
                        col_type = self._infer_type(col_values)
                        metadata["columns_info"] = metadata.get("columns_info", [])
                        metadata["columns_info"].append({
                            "name": col,
                            "type": col_type,
                            "sample_count": len(col_values)
                        })

        except Exception as e:
            return json.dumps({"error": str(e)})

        return json.dumps(metadata, indent=2, ensure_ascii=False)

    async def _extract_json_metadata(self, path: Path) -> str:
        """提取 JSON 元数据"""
        metadata = {
            "format": "JSON",
            "file": path.name,
        }

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if isinstance(data, dict):
                metadata["type"] = "object"
                metadata["keys"] = list(data.keys())
                metadata["key_count"] = len(data)
            elif isinstance(data, list):
                metadata["type"] = "array"
                metadata["length"] = len(data)
                if len(data) > 0:
                    metadata["first_item_type"] = type(data[0]).__name__
            else:
                metadata["type"] = type(data).__name__

        except Exception as e:
            return json.dumps({"error": str(e)})

        return json.dumps(metadata, indent=2, ensure_ascii=False)

    async def _extract_fits_metadata(self, path: Path) -> str:
        """提取 FITS 元数据 (天文数据格式)"""
        # 简化实现
        metadata = {
            "format": "FITS",
            "file": path.name,
            "note": "FITS 格式需要 astropy 库支持"
        }
        return json.dumps(metadata, indent=2, ensure_ascii=False)

    async def _extract_netcdf_metadata(self, path: Path) -> str:
        """提取 NetCDF 元数据"""
        # 简化实现
        metadata = {
            "format": "NetCDF",
            "file": path.name,
            "note": "NetCDF 格式需要 netCDF4 库支持"
        }
        return json.dumps(metadata, indent=2, ensure_ascii=False)

    async def _extract_generic_metadata(self, path: Path) -> str:
        """提取通用元数据"""
        stat = path.stat()

        metadata = {
            "format": "Generic",
            "file": path.name,
            "size_bytes": stat.st_size,
            "modified_time": stat.st_mtime,
        }

        return json.dumps(metadata, indent=2, ensure_ascii=False)

    def _infer_type(self, values: list) -> str:
        """推断列数据类型"""
        if not values:
            return "unknown"

        # 检查是否为数字
        numeric_count = 0
        for v in values[:10]:
            try:
                float(v)
                numeric_count += 1
            except (ValueError, TypeError):
                pass

        if numeric_count > len(values) * 0.8:
            return "numeric"

        # 检查是否为日期
        from datetime import datetime
        date_count = 0
        for v in values[:10]:
            try:
                datetime.fromisoformat(str(v).replace('/', '-'))
                date_count += 1
            except (ValueError, TypeError):
                pass

        if date_count > len(values) * 0.8:
            return "datetime"

        return "string"
