"""Configuration management."""
import os
import json
from pathlib import Path
from typing import Any, Dict, Optional, Union
from dataclasses import dataclass, field
import yaml


@dataclass
class Config:
    """Configuration container."""

    # LLM settings
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 4096

    # Agent settings
    agent_max_iterations: int = 100
    agent_timeout: int = 300

    # Session settings
    session_ttl: int = 3600
    max_sessions: int = 100

    # Storage settings
    storage_type: str = "memory"  # memory, file, sqlite
    storage_path: str = "./data"

    # Channel settings
    default_channel: str = "console"

    # Logging
    log_level: str = "INFO"
    log_file: Optional[str] = None

    # Custom settings
    extra: Dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        """Get config value by key."""
        if hasattr(self, key):
            return getattr(self, key)
        return self.extra.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set config value."""
        if hasattr(self, key):
            setattr(self, key, value)
        else:
            self.extra[key] = value

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {}
        for key, value in self.__dict__.items():
            if key == "extra":
                result.update(value)
            elif not key.startswith("_"):
                result[key] = value
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        """Create config from dictionary."""
        extra = {}
        config = cls()

        for key, value in data.items():
            if hasattr(config, key):
                setattr(config, key, value)
            else:
                extra[key] = value

        config.extra = extra
        return config

    @classmethod
    def from_file(cls, path: Union[str, Path]) -> "Config":
        """Load config from file."""
        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        if path.suffix in [".yaml", ".yml"]:
            with open(path) as f:
                data = yaml.safe_load(f)
        elif path.suffix == ".json":
            with open(path) as f:
                data = json.load(f)
        else:
            raise ValueError(f"Unsupported config format: {path.suffix}")

        return cls.from_dict(data)

    @classmethod
    def from_env(cls) -> "Config":
        """Load config from environment variables."""
        config = cls()

        # LLM settings
        if os.getenv("LLM_PROVIDER"):
            config.llm_provider = os.getenv("LLM_PROVIDER")
        if os.getenv("LLM_MODEL"):
            config.llm_model = os.getenv("LLM_MODEL")
        if os.getenv("LLM_TEMPERATURE"):
            config.llm_temperature = float(os.getenv("LLM_TEMPERATURE"))

        # Storage
        if os.getenv("STORAGE_TYPE"):
            config.storage_type = os.getenv("STORAGE_TYPE")
        if os.getenv("STORAGE_PATH"):
            config.storage_path = os.getenv("STORAGE_PATH")

        # Logging
        if os.getenv("LOG_LEVEL"):
            config.log_level = os.getenv("LOG_LEVEL")

        return config

    def merge(self, other: "Config") -> "Config":
        """Merge with another config."""
        result = Config()

        for key in self.__dict__.keys():
            if key == "extra":
                continue
            self_val = getattr(self, key)
            other_val = getattr(other, key)
            setattr(result, key, other_val if other_val != getattr(Config, key, None) else self_val)

        result.extra = {**self.extra, **other.extra}
        return result


class ConfigManager:
    """Manages configuration loading and access."""

    def __init__(self):
        self._configs: Dict[str, Config] = {}
        self._default_config: Optional[Config] = None

    def load_config(
        self,
        name: str,
        path: Optional[Union[str, Path]] = None,
        env: bool = True,
    ) -> Config:
        """Load a named config."""
        config = Config()

        # Load from file if provided
        if path:
            try:
                config = Config.from_file(path)
            except FileNotFoundError:
                pass

        # Merge with environment config
        if env:
            env_config = Config.from_env()
            config = config.merge(env_config)

        self._configs[name] = config

        if name == "default" or not self._default_config:
            self._default_config = config

        return config

    def get_config(self, name: str = "default") -> Optional[Config]:
        """Get a named config."""
        return self._configs.get(name)

    def set_default_config(self, name: str) -> bool:
        """Set the default config."""
        if name in self._configs:
            self._default_config = self._configs[name]
            return True
        return False

    @property
    def config(self) -> Config:
        """Get default config."""
        if not self._default_config:
            self._default_config = Config()
            self._configs["default"] = self._default_config
        return self._default_config
