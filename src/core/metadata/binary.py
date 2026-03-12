"""元信息提取器 - 二进制格式"""

from pathlib import Path
from typing import Any, Dict


# Magic bytes 映射表
MAGIC_BYTES = {
    # 图像
    b'\x89PNG\r\n\x1a\n': 'PNG',
    b'\xff\xd8\xff': 'JPEG',
    b'GIF87a': 'GIF',
    b'GIF89a': 'GIF',
    b'BM': 'BMP',
    
    # 压缩
    b'\x1f\x8b': 'GZIP',
    b'PK\x03\x04': 'ZIP',
    b'PK\x05\x06': 'ZIP',
    
    # HDF
    b'\x89HDF': 'HDF5',
    
    # 视频
    b'ftypmp4': 'MP4',
    b'ftypisom': 'MP4',
    b'ftypMSNV': 'MP4',
    
    # 音频
    b'RIFF': 'WAV',  # 也可能是 AVI
    
    # ELF
    b'\x7fELF': 'ELF',
    
    # PDF
    b'%PDF': 'PDF',
    
    # NumPy
    b'NUMPY': 'NUMPY',
}


def extract_binary_metadata(file_path: Path) -> Dict[str, Any]:
    """提取二进制文件元信息
    
    Args:
        file_path: 二进制文件路径
        
    Returns:
        包含二进制文件元信息的字典
    """
    metadata = {
        "file": file_path.name,
        "ext": file_path.suffix,
        "type": "binary"
    }
    
    try:
        # 读取文件头
        with open(file_path, 'rb') as f:
            header = f.read(64)
            
        # 检测 magic bytes
        magic = header[:8]
        detected_type = detect_by_magic(magic)
        if detected_type:
            metadata["detected_format"] = detected_type
            
        # 保存 magic bytes (用于调试)
        metadata["magic_bytes"] = magic[:8].hex()
        
        # 文件大小
        file_size = file_path.stat().st_size
        if file_size > 1024 * 1024 * 1024:
            metadata["size"] = f"{file_size / (1024**3):.2f} GB"
        elif file_size > 1024 * 1024:
            metadata["size"] = f"{file_size / (1024**2):.2f} MB"
        elif file_size > 1024:
            metadata["size"] = f"{file_size / 1024:.2f} KB"
        else:
            metadata["size"] = f"{file_size} bytes"
            
        # 尝试解析特定格式
        if detected_type == 'NUMPY':
            metadata.update(_extract_numpy_from_header(header))
        elif detected_type in ['JPEG', 'PNG', 'GIF', 'BMP']:
            metadata.update(_extract_image_info_from_header(header, detected_type))
            
    except Exception as e:
        # 读取失败，返回基本信息
        pass
    
    return metadata


def detect_by_magic(header: bytes) -> str:
    """通过 magic bytes 检测格式"""
    for magic, format_name in MAGIC_BYTES.items():
        if header.startswith(magic):
            return format_name
    
    # 额外检查
    if len(header) >= 4:
        # 检查更多 magic bytes
        if header[:4] == b'\x89HDF':
            return 'HDF5'
            
    return None


def _extract_numpy_from_header(header: bytes) -> Dict[str, Any]:
    """从 NumPy 文件头提取信息"""
    metadata = {}
    
    try:
        # NumPy magic: b'NUMPY' + version (2 bytes) + header length (2 bytes)
        if header[:6] == b'NUMPY':
            version = header[6:8]
            magic_len = int.from_bytes(header[8:10], 'little')
            metadata["numpy_version"] = f"{version[0]}.{version[1]}"
            metadata["numpy_header_size"] = magic_len
    except:
        pass
        
    return metadata


def _extract_image_info_from_header(header: bytes, format_type: str) -> Dict[str, Any]:
    """从文件头提取图像信息"""
    metadata = {"detected_type": "image"}
    
    try:
        if format_type == 'JPEG':
            # JPEG: 查找 SOF 标记
            metadata["format"] = "JPEG"
            
        elif format_type == 'PNG':
            # PNG: IHDR chunk 在 16-24 bytes
            if len(header) >= 24:
                width = int.from_bytes(header[16:20], 'big')
                height = int.from_bytes(header[20:24], 'big')
                metadata["width"] = width
                metadata["height"] = height
                
        elif format_type == 'BMP':
            # BMP: 文件大小在 2-6, 宽在 18-22, 高在 22-26
            if len(header) >= 26:
                size = int.from_bytes(header[2:6], 'little')
                width = int.from_bytes(header[18:22], 'little')
                height = int.from_bytes(header[22:26], 'little')
                metadata["width"] = width
                metadata["height"] = abs(height)
                
    except:
        pass
    
    return metadata
