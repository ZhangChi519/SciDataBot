"""元信息提取器 - 图像格式"""

from pathlib import Path
from typing import Any, Dict


def extract_image_metadata(file_path: Path) -> Dict[str, Any]:
    """提取图像元信息
    
    Args:
        file_path: 图像文件路径
        
    Returns:
        包含图像元信息的字典
    """
    metadata = {
        "file": file_path.name,
        "ext": file_path.suffix,
        "type": "image"
    }
    
    try:
        from PIL import Image
        with Image.open(file_path) as img:
            metadata["format"] = img.format
            metadata["width"] = img.width
            metadata["height"] = img.height
            metadata["mode"] = img.mode
            
            # 文件大小
            file_size = file_path.stat().st_size
            if file_size > 1024 * 1024:
                metadata["size_mb"] = round(file_size / (1024 * 1024), 2)
            else:
                metadata["size_kb"] = round(file_size / 1024, 2)
                
    except ImportError:
        # PIL 未安装，尝试简单读取
        try:
            file_size = file_path.stat().st_size
            metadata["size"] = file_size
        except:
            pass
    except Exception as e:
        # 读取失败，返回基本信息
        try:
            metadata["size"] = file_path.stat().st_size
        except:
            pass
    
    return metadata
