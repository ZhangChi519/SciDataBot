"""MATLAB .mat 文件提取工具 - 并行处理"""

import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
from loguru import logger

from src.tools.base import Tool, ToolResult


def _extract_tensor_info_from_mat(file_path: str) -> dict:
    """从单个 .mat 文件中提取张量信息（用于并行处理）"""
    try:
        from scipy.io import loadmat
        
        result = {
            "file": os.path.basename(file_path),
            "file_path": file_path,
            "file_size_bytes": os.path.getsize(file_path),
            "tensors": [],
            "error": None
        }
        
        data = loadmat(file_path, squeeze_me=True, struct_as_record=False)
        
        for key, value in data.items():
            if key.startswith('__'):
                continue
            
            tensor_info = {
                "name": key,
                "type": type(value).__name__,
            }
            
            if isinstance(value, np.ndarray):
                tensor_info["shape"] = list(value.shape)
                tensor_info["dtype"] = str(value.dtype)
                tensor_info["size_bytes"] = value.nbytes
                
                if value.ndim == 0:
                    tensor_info["dimensions"] = "scalar"
                    tensor_info["value"] = str(value.item())[:100]
                elif value.ndim == 1:
                    tensor_info["dimensions"] = "1D"
                    tensor_info["length"] = len(value)
                elif value.ndim == 2:
                    tensor_info["dimensions"] = "2D"
                elif value.ndim == 3:
                    tensor_info["dimensions"] = "3D"
                elif value.ndim == 4:
                    tensor_info["dimensions"] = "4D"
                else:
                    tensor_info["dimensions"] = f"{value.ndim}D"
                    
                if value.ndim > 0:
                    tensor_info["total_elements"] = int(value.size)
                    
            elif isinstance(value, (np.integer, np.floating)):
                tensor_info["dimensions"] = "scalar"
                tensor_info["value"] = str(value)
            elif isinstance(value, str):
                tensor_info["dimensions"] = "string"
                tensor_info["length"] = len(value)
                tensor_info["value"] = value[:200]
            elif isinstance(value, dict):
                tensor_info["dimensions"] = "dict"
                tensor_info["keys"] = list(value.keys())[:20]
            else:
                tensor_info["dimensions"] = "unknown"
                
            result["tensors"].append(tensor_info)
            
        result["tensor_count"] = len(result["tensors"])
        return result
        
    except Exception as e:
        return {
            "file": os.path.basename(file_path),
            "file_path": file_path,
            "error": str(e),
            "tensors": [],
            "tensor_count": 0
        }


class MatFileExtractor(Tool):
    """并行提取 MATLAB .mat 文件中的张量信息"""

    name = "extract_mat_files"
    description = "并行提取多个 MATLAB .mat 文件中的张量信息，整合到 JSON 文件"
    category = "data_processing"

    def __init__(self, max_workers: int = None):
        super().__init__()
        self.max_workers = max_workers or os.cpu_count()

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "包含 .mat 文件的目录路径"
                },
                "output_json": {
                    "type": "string",
                    "description": "输出 JSON 文件路径（可选，默认输出到目录下的 tensors_info.json）"
                },
                "max_workers": {
                    "type": "integer",
                    "description": "并行处理的最大工作线程数（可选，默认使用所有 CPU 核心）"
                },
                "pattern": {
                    "type": "string",
                    "description": "文件匹配模式（默认 *.mat）",
                    "default": "*.mat"
                }
            },
            "required": ["directory"]
        }

    async def execute(self, directory: str, output_json: str = None, 
                     max_workers: int = None, pattern: str = "*.mat", **kwargs) -> ToolResult:
        """执行并行提取"""
        
        dir_path = Path(directory)
        if not dir_path.exists():
            return ToolResult(success=False, error=f"目录不存在: {directory}")
        
        if not dir_path.is_dir():
            return ToolResult(success=False, error=f"路径不是目录: {directory}")
        
        mat_files = list(dir_path.glob(pattern))
        if not mat_files:
            return ToolResult(success=False, error=f"目录中没有找到 .mat 文件: {directory}")
        
        try:
            from scipy.io import loadmat
        except ImportError:
            return ToolResult(
                success=False,
                error="缺少依赖库 scipy，请运行 'pip install scipy' 安装后重试。",
                data={
                    "missing_dependency": "scipy",
                    "install_command": "pip install scipy",
                    "action_required": "install"
                }
            )
        
        logger.info(f"找到 {len(mat_files)} 个 .mat 文件，使用 {max_workers or self.max_workers} 个工作线程")
        
        workers = max_workers or self.max_workers
        file_paths = [str(f) for f in mat_files]
        
        all_results = []
        failed_files = []
        
        with ProcessPoolExecutor(max_workers=workers) as executor:
            future_to_file = {
                executor.submit(_extract_tensor_info_from_mat, fp): fp 
                for fp in file_paths
            }
            
            for future in as_completed(future_to_file):
                file_path = future_to_file[future]
                try:
                    result = future.result()
                    all_results.append(result)
                    if result.get("error"):
                        failed_files.append(result["file"])
                        logger.warning(f"处理失败 {result['file']}: {result['error']}")
                    else:
                        logger.info(f"成功处理 {result['file']}: {result['tensor_count']} 个张量")
                except Exception as e:
                    logger.error(f"处理异常 {file_path}: {e}")
                    failed_files.append(os.path.basename(file_path))
                    all_results.append({
                        "file": os.path.basename(file_path),
                        "file_path": file_path,
                        "error": str(e),
                        "tensors": [],
                        "tensor_count": 0
                    })
        
        summary = {
            "directory": str(dir_path.absolute()),
            "total_files": len(mat_files),
            "successful": len(all_results) - len(failed_files),
            "failed": len(failed_files),
            "failed_files": failed_files,
            "max_workers": workers,
            "files": all_results
        }
        
        if output_json is None:
            output_json = dir_path / "tensors_info.json"
        else:
            output_json = Path(output_json)
            
        output_json.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        logger.info(f"结果已保存到: {output_json}")
        
        return ToolResult(
            success=True,
            data={
                "output_file": str(output_json),
                "total_files": len(mat_files),
                "successful": len(all_results) - len(failed_files),
                "failed": len(failed_files),
                "total_tensors": sum(r.get("tensor_count", 0) for r in all_results)
            }
        )
