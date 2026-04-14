"""数据导出工具"""

import json
from pathlib import Path

from src.tools.base import Tool


class DataExporter(Tool):
    """数据导出"""

    name = "export_data"
    description = "将数据导出为各种格式"
    category = "data_integration"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "input_data": {
                    "type": "string",
                    "description": "输入数据 (JSON 字符串)"
                },
                "output_path": {
                    "type": "string",
                    "description": "输出文件路径"
                },
                "format": {
                    "type": "string",
                    "enum": ["json", "csv", "txt"],
                    "description": "输出格式"
                }
            },
            "required": ["input_data", "output_path", "format"]
        }

    async def execute(self, input_data: str, output_path: str, format: str = "json", **kwargs) -> str:
        """执行数据导出"""

        try:
            if isinstance(input_data, str):
                data = json.loads(input_data)
            else:
                data = input_data
        except json.JSONDecodeError:
            return json.dumps({"error": "无效的 JSON 数据"})

        path = Path(output_path)

        try:
            if format == "json":
                return await self._export_json(data, path)
            elif format == "csv":
                return await self._export_csv(data, path)
            elif format == "txt":
                return await self._export_txt(data, path)
            else:
                return json.dumps({"error": f"不支持的格式: {format}"})

        except Exception as e:
            return json.dumps({"error": str(e)})

    async def _export_json(self, data, path: Path) -> str:
        """导出 JSON"""
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return json.dumps({"success": True, "path": str(path), "size_bytes": path.stat().st_size})

    async def _export_csv(self, data, path: Path) -> str:
        """导出 CSV"""
        import csv

        if not isinstance(data, list) or not data:
            return json.dumps({"error": "数据必须是数组"})

        path.parent.mkdir(parents=True, exist_ok=True)

        # 获取列名
        if isinstance(data[0], dict):
            fieldnames = list(data[0].keys())
        else:
            return json.dumps({"error": "CSV 导出需要字典列表"})

        with open(path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)

        return json.dumps({"success": True, "path": str(path), "size_bytes": path.stat().st_size})

    async def _export_txt(self, data, path: Path) -> str:
        """导出 TXT"""
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, 'w', encoding='utf-8') as f:
            if isinstance(data, list):
                for item in data:
                    f.write(str(item) + "\n")
            else:
                f.write(str(data))

        return json.dumps({"success": True, "path": str(path), "size_bytes": path.stat().st_size})
