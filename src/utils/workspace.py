"""Workspace utilities for channel-based session management."""

import os
from pathlib import Path
from datetime import datetime
from typing import Optional


def sanitize_dirname(name: str) -> str:
    """Sanitize directory name by removing/replacing invalid characters.
    
    Args:
        name: The name to sanitize (e.g., channel type, chat_id)
        
    Returns:
        Sanitized directory name safe for filesystem
    """
    # Replace invalid chars with underscore
    sanitized = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    return sanitized[:255]


def get_channel_dir(workspace: Path, channel: str, chat_id: Optional[str] = None) -> Path:
    """Get the directory for a specific channel and chat_id.
    
    Args:
        workspace: Root workspace directory
        channel: Channel type (e.g., 'console', 'telegram', 'feishu', 'webhook')
        chat_id: Optional chat/user identifier
        
    Returns:
        Path to the channel directory
    """
    # Build directory name: channel or channel_chatid
    if chat_id:
        dir_name = f"{sanitize_dirname(channel)}_{sanitize_dirname(chat_id)}"
    else:
        dir_name = sanitize_dirname(channel)
    
    channel_dir = workspace / dir_name
    channel_dir.mkdir(parents=True, exist_ok=True)
    return channel_dir


def get_session_dirs(channel_dir: Path) -> dict[str, Path]:
    """Get all session subdirectories.
    
    Args:
        channel_dir: The channel directory path
        
    Returns:
        Dictionary mapping subdirectory names to paths
    """
    # Create subdirectories
    dirs = {
        "root": channel_dir,
        "session": channel_dir / "session.jsonl",
        "memory": channel_dir / "memory",
        "logs": channel_dir / "logs",
        "intermediates": channel_dir / "intermediates",
        "results": channel_dir / "results",
    }
    
    # Ensure directories exist
    for name, path in dirs.items():
        if name != "session":  # session is a file
            path.mkdir(parents=True, exist_ok=True)
    
    return dirs


def get_log_file_path(logs_dir: Path) -> Path:
    """Get today's log file path.
    
    Args:
        logs_dir: The logs directory
        
    Returns:
        Path to today's log file
    """
    today = datetime.now().strftime("%Y-%m-%d")
    return logs_dir / f"{today}.log"


def get_intermediate_file_path(
    intermediates_dir: Path,
    request_id: str,
    task_id: int,
    agent_idx: int = 0
) -> Path:
    """Get path for intermediate result file.
    
    Args:
        intermediates_dir: The intermediates directory
        request_id: The request identifier
        task_id: The task identifier
        agent_idx: The agent index (for parallel tasks)
        
    Returns:
        Path to the intermediate result file
    """
    filename = f"task_{request_id}_{task_id}_{agent_idx}.json"
    return intermediates_dir / filename


def cleanup_session(channel_dir: Path) -> bool:
    """Clean up a session directory.
    
    Args:
        channel_dir: The channel directory to clean up
        
    Returns:
        True if cleanup successful
    """
    import shutil
    
    try:
        if channel_dir.exists():
            shutil.rmtree(channel_dir)
        return True
    except Exception:
        return False
