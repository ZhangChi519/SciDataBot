"""元信息提取器 - 点云格式"""

from pathlib import Path
from typing import Any, Dict


def extract_pointcloud_metadata(file_path: Path) -> Dict[str, Any]:
    """提取点云元信息
    
    支持格式: .pcd, .ply, .las, .laz, .xyz
    
    Args:
        file_path: 点云文件路径
        
    Returns:
        包含点云元信息的字典
    """
    metadata = {
        "file": file_path.name,
        "ext": file_path.suffix,
        "type": "pointcloud"
    }
    
    try:
        ext = file_path.suffix.lower()
        
        if ext == '.pcd':
            metadata.update(_extract_pcd_metadata(file_path))
        elif ext == '.ply':
            metadata.update(_extract_ply_metadata(file_path))
        elif ext in ['.las', '.laz']:
            metadata.update(_extract_las_metadata(file_path))
        elif ext == '.xyz':
            metadata.update(_extract_xyz_metadata(file_path))
            
    except Exception as e:
        # 读取失败，返回基本信息
        pass
    
    # 添加文件大小
    try:
        file_size = file_path.stat().st_size
        if file_size > 1024 * 1024:
            metadata["size_mb"] = round(file_size / (1024 * 1024), 2)
        else:
            metadata["size_kb"] = round(file_size / 1024, 2)
    except:
        pass
    
    return metadata


def _extract_pcd_metadata(file_path: Path) -> Dict[str, Any]:
    """提取 PCD 格式元信息"""
    metadata = {"format": "PCD"}
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if line.startswith('VERSION'):
                    metadata['version'] = line.split()[-1]
                elif line.startswith('FIELDS'):
                    metadata['fields'] = line.split()[1:]
                elif line.startswith('SIZE'):
                    sizes = line.split()[1:]
                    metadata['sizes'] = [int(s) for s in sizes]
                elif line.startswith('TYPE'):
                    types = line.split()[1:]
                    metadata['types'] = types
                elif line.startswith('COUNT'):
                    metadata['count'] = [int(c) for c in line.split()[1:]]
                elif line.startswith('WIDTH'):
                    metadata['width'] = int(line.split()[1])
                elif line.startswith('HEIGHT'):
                    metadata['height'] = int(line.split()[1])
                elif line.startswith('POINTS'):
                    metadata['points'] = int(line.split()[1])
                elif line.startswith('DATA'):
                    metadata['data_type'] = line.split()[1]
                    break
                    
    except Exception as e:
        pass
    
    return metadata


def _extract_ply_metadata(file_path: Path) -> Dict[str, Any]:
    """提取 PLY 格式元信息"""
    metadata = {"format": "PLY"}
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if line.startswith('element vertex'):
                    metadata['vertices'] = int(line.split()[2])
                elif line.startswith('element face'):
                    metadata['faces'] = int(line.split()[2])
                elif line.startswith('property'):
                    metadata.setdefault('properties', []).append(line)
                elif line.startswith('end_header'):
                    break
                    
    except Exception as e:
        pass
    
    return metadata


def _extract_las_metadata(file_path: Path) -> Dict[str, Any]:
    """提取 LAS/LAZ 格式元信息"""
    metadata = {"format": "LAS"}
    
    try:
        # LAS 文件有固定的 header 大小 (227 bytes for LAS 1.2)
        with open(file_path, 'rb') as f:
            # 读取 signature
            signature = f.read(4)
            if signature == b'LASF':
                # 读取 header fields
                f.seek(36)
                point_count = int.from_bytes(f.read(8), 'little')
                metadata['points'] = point_count
    except Exception as e:
        pass
    
    return metadata


def _extract_xyz_metadata(file_path: Path) -> Dict[str, Any]:
    """提取 XYZ 格式元信息"""
    metadata = {"format": "XYZ"}
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            # 尝试读取第一行确定格式
            first_line = f.readline().strip()
            if first_line:
                parts = first_line.split()
                metadata['columns'] = len(parts)
                # 估算点数
                file_size = file_path.stat().st_size
                est_points = file_size // (len(parts) * 10)  # 假设每点约10字节
                metadata['estimated_points'] = est_points
    except Exception as e:
        pass
    
    return metadata
