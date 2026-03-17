"""元数据提取工具 - 支持多种数据格式"""

import json
from pathlib import Path
from typing import Any, Dict

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

        # 图像格式
        if suffix in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.tif', '.webp']:
            return await self._extract_image_metadata(path)
        # NumPy 格式
        elif suffix in ['.npy', '.npz']:
            return await self._extract_numpy_metadata(path)
        # 点云格式
        elif suffix in ['.pcd', '.ply', '.las', '.laz', '.xyz', '.xyzrgb']:
            return await self._extract_pointcloud_metadata(path)
        # 视频格式
        elif suffix in ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv']:
            return await self._extract_video_metadata(path)
        # CSV
        elif suffix == '.csv':
            return await self._extract_csv_metadata(path, deep)
        # JSON
        elif suffix == '.json':
            return await self._extract_json_metadata(path)
        # FITS (天文)
        elif suffix == '.fits' or suffix == '.fit':
            return await self._extract_fits_metadata(path)
        # NetCDF
        elif suffix == '.nc':
            return await self._extract_netcdf_metadata(path)
        else:
            return await self._extract_binary_metadata(path)

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

    async def _extract_image_metadata(self, path: Path) -> str:
        """提取图像元数据"""
        metadata: Dict[str, Any] = {
            "format": "Image",
            "file": path.name,
            "type": "image"
        }

        try:
            from PIL import Image
            with Image.open(path) as img:
                metadata["image_format"] = img.format
                metadata["width"] = img.width
                metadata["height"] = img.height
                metadata["mode"] = img.mode

                file_size = path.stat().st_size
                if file_size > 1024 * 1024:
                    metadata["size_mb"] = round(file_size / (1024 * 1024), 2)
                else:
                    metadata["size_kb"] = round(file_size / 1024, 2)

        except ImportError:
            metadata["note"] = "PIL not installed, limited info"
        except Exception as e:
            metadata["error"] = str(e)

        return json.dumps(metadata, indent=2, ensure_ascii=False)

    async def _extract_numpy_metadata(self, path: Path) -> str:
        """提取 NumPy 数组元数据"""
        metadata: Dict[str, Any] = {
            "format": "NumPy",
            "file": path.name,
            "type": "array"
        }

        try:
            import numpy as np
            arr = np.load(path, allow_pickle=True)
            
            if isinstance(arr, dict):
                metadata["type"] = "dict"
                metadata["keys"] = list(arr.keys())
                metadata["key_count"] = len(arr.keys())
            elif isinstance(arr, np.ndarray):
                metadata["dtype"] = str(arr.dtype)
                metadata["shape"] = arr.shape
                metadata["ndim"] = arr.ndim
                metadata["size"] = arr.size
            else:
                metadata["type"] = type(arr).__name__

        except ImportError:
            metadata["note"] = "numpy not installed"
        except Exception as e:
            metadata["error"] = str(e)

        return json.dumps(metadata, indent=2, ensure_ascii=False)

    async def _extract_pointcloud_metadata(self, path: Path) -> str:
        """提取点云元数据"""
        metadata: Dict[str, Any] = {
            "format": "PointCloud",
            "file": path.name,
            "type": "pointcloud"
        }

        suffix = path.suffix.lower()
        metadata["point_format"] = suffix[1:]

        try:
            if suffix == '.ply':
                metadata.update(self._extract_ply_metadata(path))
            elif suffix == '.pcd':
                metadata.update(self._extract_pcd_metadata(path))
            elif suffix in ['.las', '.laz']:
                metadata.update(self._extract_las_metadata(path))
            elif suffix in ['.xyz', '.xyzrgb']:
                metadata.update(self._extract_xyz_metadata(path))
        except Exception as e:
            metadata["error"] = str(e)

        return json.dumps(metadata, indent=2, ensure_ascii=False)

    def _extract_ply_metadata(self, path: Path) -> Dict[str, Any]:
        """提取 PLY 元数据"""
        metadata: Dict[str, Any] = {}
        point_count = 0
        
        with open(path, 'r') as f:
            for line in f:
                if line.startswith('element vertex'):
                    point_count = int(line.split()[-1])
                    break
        
        metadata["point_count"] = point_count
        return metadata

    def _extract_pcd_metadata(self, path: Path) -> Dict[str, Any]:
        """提取 PCD 元数据"""
        metadata: Dict[str, Any] = {}
        point_count = 0
        
        with open(path, 'r') as f:
            for line in f:
                if line.startswith('POINTS'):
                    point_count = int(line.split()[-1])
                    break
        
        metadata["point_count"] = point_count
        return metadata

    def _extract_las_metadata(self, path: Path) -> Dict[str, Any]:
        """提取 LAS 元数据"""
        metadata: Dict[str, Any] = {}
        
        try:
            import numpy as np
            data = np.fromfile(path, dtype=np.uint8)
            if len(data) >= 148:
                point_count = int.from_bytes(data[107:111], 'little')
                metadata["point_count"] = point_count
        except:
            pass
        
        return metadata

    def _extract_xyz_metadata(self, path: Path) -> Dict[str, Any]:
        """提取 XYZ 元数据"""
        metadata: Dict[str, Any] = {}
        
        try:
            with open(path, 'r') as f:
                for i, line in enumerate(f):
                    if i >= 100:
                        break
            metadata["estimated_points"] = i + 1
        except:
            pass
        
        return metadata

    async def _extract_video_metadata(self, path: Path) -> str:
        """提取视频元数据"""
        metadata: Dict[str, Any] = {
            "format": "Video",
            "file": path.name,
            "type": "video"
        }

        stat = path.stat()
        metadata["size_bytes"] = stat.st_size
        metadata["size_mb"] = round(stat.st_size / (1024 * 1024), 2)

        try:
            import cv2
            cap = cv2.VideoCapture(str(path))
            if cap.isOpened():
                metadata["width"] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                metadata["height"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                metadata["fps"] = cap.get(cv2.CAP_PROP_FPS)
                metadata["frame_count"] = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                cap.release()
        except ImportError:
            metadata["note"] = "OpenCV not installed"
        except Exception as e:
            metadata["error"] = str(e)

        return json.dumps(metadata, indent=2, ensure_ascii=False)

    async def _extract_binary_metadata(self, path: Path) -> str:
        """提取通用二进制文件元数据"""
        metadata: Dict[str, Any] = {
            "format": "Binary",
            "file": path.name,
            "type": "binary"
        }

        stat = path.stat()
        metadata["size_bytes"] = stat.st_size
        metadata["modified_time"] = stat.st_mtime

        # 尝试检测文件头
        try:
            with open(path, 'rb') as f:
                header = f.read(16)
                
            # 检测常见格式
            if header[:4] == b'\x89PNG':
                metadata["detected_type"] = "PNG image"
            elif header[:2] == b'\xff\xd8':
                metadata["detected_type"] = "JPEG image"
            elif header[:4] == b'RIFF' and header[8:12] == b'WEBP':
                metadata["detected_type"] = "WebP image"
            elif header[:4] == b'PK\x03\x04':
                metadata["detected_type"] = "ZIP archive"
            elif header[:4] == b'GZIP':
                metadata["detected_type"] = "GZIP archive"

        except Exception as e:
            metadata["header_error"] = str(e)

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
