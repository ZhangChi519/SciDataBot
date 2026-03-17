"""Path configuration utilities."""

from pathlib import Path

from src.config.loader import get_config_path


def get_workspace_path(config_path: Path | None = None) -> Path:
    """Get the workspace path from config."""
    from src.config.loader import load_config

    config = load_config(config_path)
    return config.workspace_path


def get_runtime_subdir(name: str) -> Path:
    """Get a runtime subdirectory under the config directory."""
    config_path = get_config_path()
    return config_path.parent / "runtime" / name


def get_cli_history_path() -> Path:
    """Get the CLI history file path."""
    return get_runtime_subdir("history")


def get_cron_dir() -> Path:
    """Get the cron jobs directory."""
    return get_runtime_subdir("cron")


def get_bridge_install_dir() -> Path:
    """Get the bridge installation directory."""
    from nanobot.config.paths import get_bridge_install_dir as nb_get_bridge_install_dir

    return nb_get_bridge_install_dir()


def get_legacy_sessions_dir() -> Path:
    """Get the legacy sessions directory."""
    return Path.home() / ".scidatabot" / "sessions"
