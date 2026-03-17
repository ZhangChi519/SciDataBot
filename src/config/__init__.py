"""Configuration module - Simple YAML-based config."""

import os
import yaml
from pathlib import Path
from typing import Any, Dict, Optional


class Config:
    """Simple configuration container."""

    def __init__(self, data: Dict[str, Any] = None):
        self._data = data or {}

    def get(self, key: str, default: Any = None) -> Any:
        """Get config value by key (supports dot notation)."""
        keys = key.split(".")
        value = self._data
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default

    def __getitem__(self, key: str) -> Any:
        return self.get(key)

    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None


class ConfigManager:
    """Simple config manager."""

    def __init__(self):
        self._configs: Dict[str, Config] = {}

    def load(self, config: Config, name: str = "default") -> Config:
        self._configs[name] = config
        return config

    def get(self, name: str = "default") -> Config:
        return self._configs.get(name, Config())


# Default config path
DEFAULT_CONFIG = Path.home() / ".scidatabot" / "config.yaml"


def get_config_path() -> Path:
    """Get config path."""
    return DEFAULT_CONFIG


def load_config(config_path: str = None) -> Config:
    """Load config from YAML file."""
    path = Path(config_path) if config_path else DEFAULT_CONFIG
    if path.exists():
        with open(path) as f:
            data = yaml.safe_load(f) or {}
            return Config(data)
    return Config()


def save_config(config: Config, config_path: str = None) -> None:
    """Save config to YAML file."""
    path = Path(config_path) if config_path else DEFAULT_CONFIG
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(config._data, f)


def set_config_path(path: Path) -> None:
    """Set config path (for compatibility)."""
    global DEFAULT_CONFIG
    DEFAULT_CONFIG = path


def get_workspace_path(config_path: str = None) -> Path:
    """Get workspace path from config."""
    config = load_config(config_path)
    workspace = config.get("workspace", "~/.scidatabot")
    return Path(workspace).expanduser()


def get_runtime_subdir(name: str) -> Path:
    """Get runtime subdirectory."""
    return DEFAULT_CONFIG.parent / "runtime" / name


def get_cli_history_path() -> Path:
    """Get CLI history path."""
    return get_runtime_subdir("history")


def get_cron_dir() -> Path:
    """Get cron jobs directory."""
    return get_runtime_subdir("cron")


def get_bridge_install_dir() -> Path:
    """Get bridge installation directory."""
    return Path.home() / ".scidatabot" / "bridge"


__all__ = [
    "Config",
    "ConfigManager",
    "get_config_path",
    "load_config",
    "save_config",
    "set_config_path",
    "get_workspace_path",
    "get_runtime_subdir",
    "get_cli_history_path",
    "get_cron_dir",
    "get_bridge_install_dir",
]
