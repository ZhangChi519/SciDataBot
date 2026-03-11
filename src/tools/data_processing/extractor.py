"""数据抽取工具"""

import json
from pathlib import Path

from src.tools.base import Tool


class DataExtractor(Tool):
    """从数据源抽取数据"""

    name = "extract_data"
    description = "从数据文件中抽取数据"
    category = "data_processing"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "数据文件路径"
                },
                "columns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要抽取的列（可选）"
                },
                "start_row": {
                    "type": "integer",
                    "description": "起始行",
                    "default": 0
                },
                "max_rows": {
                    "type": "integer",
                    "description": "最大行数",
                    "default": 1000
                }
            },
            "required": ["file_path"]
        }

    async def execute(self, file_path: str, columns: list = None,
                      start_row: int = 0, max_rows: int = 1000, **kwargs) -> str:
        """执行数据抽取"""

        path = Path(file_path)

        if not path.exists():
            return json.dumps({"error": f"文件不存在: {file_path}"})

        suffix = path.suffix.lower()

        if suffix == '.csv':
            return await self._extract_csv(path, columns, start_row, max_rows)
        elif suffix == '.json':
            return await self._extract_json(path, max_rows)
        else:
            return json.dumps({"error": f"不支持的格式: {suffix}"})

    async def _extract_csv(self, path: Path, columns: list, start_row: int, max_rows: int) -> str:
        """抽取 CSV 数据"""
        import csv

        result = {
            "format": "CSV",
            "file": path.name,
            "data": [],
            "columns": [],
        }

        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                reader = csv.reader(f)
                headers = next(reader)
                result["columns"] = headers

                # 确定要抽取的列索引
                col_indices = None
                if columns:
                    col_indices = [headers.index(c) for c in columns if c in headers]
                else:
                    col_indices = list(range(len(headers)))

                # 跳过起始行
                for _ in range(start_row):
                    next(reader)

                # 抽取数据
                for i, row in enumerate(reader):
                    if i >= max_rows:
                        break
                    if col_indices:
                        result["data"].append([row[i] for i in col_indices if i < len(row)])
                    else:
                        result["data"].append(row)

            result["row_count"] = len(result["data"])

        except Exception as e:
            return json.dumps({"error": str(e)})

        return json.dumps(result, indent=2, ensure_ascii=False)

    async def _extract_json(self, path: Path, max_rows: int) -> str:
        """抽取 JSON 数据"""
        import json

        result = {
            "format": "JSON",
            "file": path.name,
        }

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if isinstance(data, list):
                result["data"] = data[:max_rows]
                result["row_count"] = len(result["data"])
            elif isinstance(data, dict):
                result["data"] = data

        except Exception as e:
            return json.dumps({"error": str(e)})

        return json.dumps(result, indent=2, ensure_ascii=False)
