"""Logging utilities for channel-specific logging."""

from pathlib import Path
from loguru import logger


def add_channel_logging(channel_dir: Path) -> None:
    """Add logging handler for a specific channel directory.
    
    Args:
        channel_dir: The channel directory path for logs
    """
    logs_dir = channel_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = logs_dir / "{time}.log"
    
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )
    
    logger.add(
        log_file,
        format=log_format,
        level="INFO",
        rotation="1 day",  # Rotate daily
        retention="30 days",  # Keep 30 days
        compression="gz",  # Compress old logs
    )
