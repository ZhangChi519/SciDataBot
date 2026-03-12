"""文件格式注册表 - 自动检测和处理未知格式"""

from pathlib import Path
from typing import Callable, Any, Dict
import logging

logger = logging.getLogger(__name__)


class FormatHandlerRegistry:
    """格式处理器注册表 - 扩展点"""
    
    FORMATTERS: Dict[str, Dict[str, Any]] = {}
    
    @classmethod
    def register(cls, format_name: str, extensions: list, handler: Callable):
        """注册格式处理器
        
        Args:
            format_name: 格式名称 (如 'image', 'pointcloud')
            extensions: 文件扩展名列表 (如 ['.png', '.jpg'])
            handler: 元信息提取函数
        """
        cls.FORMATTERS[format_name] = {
            'extensions': [ext.lower() for ext in extensions],
            'handler': handler,
        }
        logger.debug(f"注册格式处理器: {format_name} -> {extensions}")
    
    @classmethod
    def detect_format(cls, file_path: Path) -> str:
        """检测文件格式
        
        Args:
            file_path: 文件路径
            
        Returns:
            格式名称 (如 'image'), 未知返回 'unknown'
        """
        ext = file_path.suffix.lower()
        
        # 遍历已注册的格式
        for format_name, config in cls.FORMATTERS.items():
            if ext in config['extensions']:
                return format_name
        
        return 'unknown'
    
    @classmethod
    def get_handler(cls, format_name: str) -> Callable:
        """获取格式处理器
        
        Args:
            format_name: 格式名称
            
        Returns:
            元信息提取函数
        """
        formatter = cls.FORMATTERS.get(format_name)
        if formatter:
            return formatter['handler']
        
        # 返回默认处理器
        return default_extract_metadata
    
    @classmethod
    def get_all_extensions(cls) -> Dict[str, list]:
        """获取所有已注册的扩展名"""
        return {
            name: config['extensions'] 
            for name, config in cls.FORMATTERS.items()
        }


# ============================================================
# 默认处理器
# ============================================================

def default_extract_metadata(file_path: Path) -> dict:
    """默认元信息提取 - 所有文件都提取的基本信息"""
    try:
        stat = file_path.stat()
        return {
            "file": file_path.name,
            "ext": file_path.suffix,
            "size": stat.st_size,
            "type": "unknown"
        }
    except Exception as e:
        logger.warning(f"提取文件元信息失败 {file_path}: {e}")
        return {
            "file": file_path.name,
            "ext": file_path.suffix,
            "size": 0,
            "type": "unknown"
        }


# ============================================================
# 注册所有内置格式处理器
# ============================================================

def _register_builtin_formatters():
    """注册内置格式处理器"""
    from .metadata.image import extract_image_metadata
    from .metadata.pointcloud import extract_pointcloud_metadata
    from .metadata.numpy import extract_numpy_metadata
    from .metadata.video import extract_video_metadata
    from .metadata.binary import extract_binary_metadata
    
    # 图像格式
    FormatHandlerRegistry.register('image', [
        '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff', '.tif', 
        '.webp', '.ico', '.svg'
    ], extract_image_metadata)
    
    # 点云格式
    FormatHandlerRegistry.register('pointcloud', [
        '.pcd', '.ply', '.las', '.laz', '.xyz'
    ], extract_pointcloud_metadata)
    
    # NumPy 格式
    FormatHandlerRegistry.register('numpy', [
        '.npy', '.npz'
    ], extract_numpy_metadata)
    
    # 视频格式
    FormatHandlerRegistry.register('video', [
        '.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv'
    ], extract_video_metadata)
    
    # 音频格式
    FormatHandlerRegistry.register('audio', [
        '.wav', '.mp3', '.flac', '.aac', '.ogg', '.m4a'
    ], extract_video_metadata)  # 复用视频提取器
    
    # 二进制格式
    FormatHandlerRegistry.register('binary', [
        '.bin', '.dat', '.raw', '.img', '.dmg'
    ], extract_binary_metadata)
    
    logger.info(f"已注册 {len(FormatHandlerRegistry.FORMATTERS)} 个格式处理器")


# 启动时自动注册
_register_builtin_formatters()
