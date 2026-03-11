"""格式检测工具"""

import os
from pathlib import Path
from typing import Any

from src.tools.base import Tool


class FormatDetector(Tool):
    """检测数据格式"""

    name = "detect_format"
    description = "检测数据文件格式、结构和元数据"
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
                "sample_size": {
                    "type": "integer",
                    "description": "采样大小",
                    "default": 1000
                }
            },
            "required": ["file_path"]
        }

    async def execute(self, file_path: str, sample_size: int = 1000, **kwargs) -> str:
        """执行格式检测"""

        path = Path(file_path)

        if not path.exists():
            return f'{{"error": "文件不存在: {file_path}"}}'

        # 检测格式
        format_info = self._detect_format(path, sample_size)

        return format_info

    def _detect_format(self, path: Path, sample_size: int) -> str:
        """实际检测逻辑"""

        suffix = path.suffix.lower()

        # 按扩展名初步判断
        format_map = {
            ".csv": "CSV (逗号分隔值)",
            ".tsv": "TSV (制表符分隔)",
            ".json": "JSON",
            ".jsonl": "JSONL",
            ".xml": "XML",
            ".fits": "FITS (天文)",
            ".nc": "NetCDF",
            ".h5": "HDF5",
            ".hdf5": "HDF5",
            ".parquet": "Parquet",
            ".feather": "Feather",
            ".pkl": "Pickle",
            ".pickle": "Pickle",
            ".npy": "NumPy Array",
            ".npz": "NumPy Archive",
            ".mat": "MATLAB",
            ".txt": "Text",
            ".log": "Log",
            ".dat": "Binary Data",
            ".bin": "Binary Data",
            ".gz": "Gzip Compressed",
            ".zip": "ZIP Archive",
            ".tar": "Tape Archive",
        }

        format_type = format_map.get(suffix, "Unknown")

        # 尝试检测魔数 (文件头)
        magic_numbers = {
            b'\x89PNG': "PNG Image",
            b'\xff\xd8\xff': "JPEG Image",
            b'GIF87a': "GIF",
            b'GIF89a': "GIF",
            b'IDL': "IDL",
            b'\x1f\x8b': "Gzip",
            b'PK\x03\x04': "ZIP",
        }

        file_format = format_type
        try:
            with open(path, 'rb') as f:
                header = f.read(16)
                for magic, fmt in magic_numbers.items():
                    if header.startswith(magic):
                        file_format = fmt
                        break
        except Exception:
            pass

        # 获取文件信息
        stat = path.stat()

        # 尝试获取行数（仅对文本文件）
        line_count = None
        if suffix in ['.csv', '.tsv', '.txt', '.log', '.jsonl']:
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    line_count = sum(1 for _ in f)
            except Exception:
                pass

        import json
        result = {
            "file": path.name,
            "format": file_format,
            "size_bytes": stat.st_size,
            "size_mb": round(stat.st_size / 1024 / 1024, 2),
            "extension": suffix,
            "modified_time": stat.st_mtime,
        }

        if line_count is not None:
            result["line_count"] = line_count

        return json.dumps(result, indent=2, ensure_ascii=False)
