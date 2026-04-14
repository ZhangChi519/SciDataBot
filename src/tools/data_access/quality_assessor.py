"""数据质量评估工具"""

import json
from pathlib import Path

from src.tools.base import Tool


class QualityAssessor(Tool):
    """评估数据质量"""

    name = "assess_quality"
    description = "评估数据质量，包括完整性、一致性、准确性等"
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
                "checks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要进行的检查项",
                    "default": ["completeness", "consistency"]
                }
            },
            "required": ["file_path"]
        }

    async def execute(self, file_path: str, checks: list = None, **kwargs) -> str:
        """执行质量评估"""

        path = Path(file_path)

        if not path.exists():
            return json.dumps({"error": f"文件不存在: {file_path}"})

        checks = checks or ["completeness", "consistency"]

        results = {
            "file": path.name,
            "checks": {}
        }

        suffix = path.suffix.lower()

        # 对 CSV 进行质量评估
        if suffix == '.csv':
            if "completeness" in checks:
                results["checks"]["completeness"] = await self._check_completeness(path)
            if "consistency" in checks:
                results["checks"]["consistency"] = await self._check_consistency(path)
        else:
            results["note"] = f"当前仅支持 CSV 格式的详细评估，其他格式: {suffix}"

        # 计算总体分数
        scores = [c.get("score", 0) for c in results["checks"].values() if isinstance(c, dict)]
        results["overall_score"] = sum(scores) / len(scores) if scores else 0

        return json.dumps(results, indent=2, ensure_ascii=False)

    async def _check_completeness(self, path: Path) -> dict:
        """检查数据完整性"""
        import csv

        total_rows = 0
        empty_rows = 0

        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                reader = csv.reader(f)
                headers = next(reader)
                column_count = len(headers)

                for row in reader:
                    total_rows += 1
                    if not any(row):  # 全空行
                        empty_rows += 1

            completeness = (total_rows - empty_rows) / total_rows if total_rows > 0 else 0

            return {
                "total_rows": total_rows,
                "empty_rows": empty_rows,
                "columns": column_count,
                "score": completeness,
                "status": "good" if completeness > 0.95 else "warning" if completeness > 0.8 else "poor"
            }

        except Exception as e:
            return {"error": str(e)}

    async def _check_consistency(self, path: Path) -> dict:
        """检查数据一致性"""
        import csv

        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                reader = csv.reader(f)
                headers = next(reader)
                column_count = len(headers)

                inconsistent_rows = 0
                total_rows = 0

                for row in reader:
                    total_rows += 1
                    if len(row) != column_count:
                        inconsistent_rows += 1

            consistency = (total_rows - inconsistent_rows) / total_rows if total_rows > 0 else 0

            return {
                "total_rows": total_rows,
                "inconsistent_rows": inconsistent_rows,
                "score": consistency,
                "status": "good" if consistency > 0.98 else "warning" if consistency > 0.9 else "poor"
            }

        except Exception as e:
            return {"error": str(e)}
