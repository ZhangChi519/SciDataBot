"""元信息提取器 - NumPy 格式"""

from pathlib import Path
from typing import Any, Dict


def extract_numpy_metadata(file_path: Path) -> Dict[str, Any]:
    """提取 NumPy 元信息
    
    支持格式: .npy, .npz
    
    Args:
        file_path: NumPy 文件路径
        
    Returns:
        包含 NumPy 元信息的字典
    """
    metadata = {
        "file": file_path.name,
        "ext": file_path.suffix,
        "type": "numpy"
    }
    
    try:
        import numpy as np
        
        ext = file_path.suffix.lower()
        
        if ext == '.npy':
            # 单个 .npy 文件
            arr = np.load(file_path, mmap_mode='r')
            if isinstance(arr, np.ndarray):
                metadata["shape"] = list(arr.shape)
                metadata["dtype"] = str(arr.dtype)
                metadata["ndim"] = arr.ndim
                metadata["size"] = arr.size
                
        elif ext == '.npz':
            # .npz 文件包含多个数组
            with np.load(file_path, mmap_mode='r') as npz:
                metadata["arrays"] = list(npz.keys())
                metadata["array_count"] = len(npz.keys())
                
                # 获取第一个数组的信息作为参考
                if len(npz.keys()) > 0:
                    first_key = list(npz.keys())[0]
                    arr = npz[first_key]
                    metadata["sample_shape"] = list(arr.shape)
                    metadata["sample_dtype"] = str(arr.dtype)
                    
    except ImportError:
        # NumPy 未安装
        pass
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
