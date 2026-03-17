"""元信息提取器 - 视频/音频格式"""

from pathlib import Path
from typing import Any, Dict


def extract_video_metadata(file_path: Path) -> Dict[str, Any]:
    """提取视频/音频元信息
    
    支持格式: 视频 (.mp4, .avi, .mov, .mkv), 音频 (.wav, .mp3, .flac)
    
    Args:
        file_path: 视频/音频文件路径
        
    Returns:
        包含视频/音频元信息的字典
    """
    metadata = {
        "file": file_path.name,
        "ext": file_path.suffix,
        "type": "video" if file_path.suffix.lower() in ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv'] else "audio"
    }
    
    # 添加文件大小
    try:
        file_size = file_path.stat().st_size
        if file_size > 1024 * 1024 * 1024:
            metadata["size_gb"] = round(file_size / (1024 * 1024 * 1024), 2)
        elif file_size > 1024 * 1024:
            metadata["size_mb"] = round(file_size / (1024 * 1024), 2)
        else:
            metadata["size_kb"] = round(file_size / 1024, 2)
    except:
        pass
    
    # 尝试使用 ffprobe 获取详细信息
    try:
        import subprocess
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 
             'format=duration,size,bit_rate:stream=codec_name,width,height,sample_rate',
             '-of', 'json', str(file_path)],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            import json
            info = json.loads(result.stdout)
            
            # 格式信息
            if 'format' in info:
                fmt = info['format']
                if 'duration' in fmt:
                    duration = float(fmt['duration'])
                    metadata['duration_sec'] = round(duration, 2)
                    # 转换为更友好的格式
                    minutes = int(duration // 60)
                    seconds = int(duration % 60)
                    metadata['duration'] = f"{minutes:02d}:{seconds:02d}"
                if 'bit_rate' in fmt:
                    metadata['bit_rate'] = int(fmt['bit_rate'])
                    
            # 视频流信息
            if 'streams' in info:
                for stream in info['streams']:
                    if stream.get('codec_type') == 'video':
                        metadata['codec'] = stream.get('codec_name')
                        if 'width' in stream:
                            metadata['width'] = stream['width']
                        if 'height' in stream:
                            metadata['height'] = stream['height']
                        break
                    elif stream.get('codec_type') == 'audio':
                        if 'sample_rate' in stream:
                            metadata['sample_rate'] = stream['sample_rate']
                        if 'codec_name' in stream:
                            metadata['audio_codec'] = stream['codec_name']
                            
    except (ImportError, FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        # ffprobe 不可用，使用基本方法
        pass
    except Exception as e:
        pass
    
    return metadata
