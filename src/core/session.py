"""Session management for conversation history."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class Session:
    """会话管理 - 使用 JSONL 持久化"""

    def __init__(
        self,
        key: str,
        workspace: Path | None = None,
        messages: list[dict] | None = None,
        last_consolidated: int = 0,
    ):
        self.key = key
        self.messages: list[dict] = messages or []
        self.last_consolidated = last_consolidated
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self._workspace = workspace

    def get_history(self, max_messages: int = 50) -> list[dict]:
        """获取最近的会话历史"""
        return self.messages[-max_messages:] if self.messages else []

    def add_message(self, role: str, content: str, **kwargs) -> None:
        """添加消息到会话"""
        msg = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        }
        if kwargs:
            msg.update(kwargs)
        self.messages.append(msg)
        self.updated_at = datetime.now()

    def clear(self) -> None:
        """清空会话历史"""
        self.messages = []
        self.last_consolidated = 0
        self.updated_at = datetime.now()

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "key": self.key,
            "messages": self.messages,
            "last_consolidated": self.last_consolidated,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @staticmethod
    def from_dict(data: dict) -> "Session":
        """从字典创建"""
        session = Session(
            key=data.get("key", ""),
            messages=data.get("messages", []),
            last_consolidated=data.get("last_consolidated", 0),
        )
        if "created_at" in data:
            session.created_at = datetime.fromisoformat(data["created_at"])
        if "updated_at" in data:
            session.updated_at = datetime.fromisoformat(data["updated_at"])
        return session

    def save_to_file(self, dir_path: Path, filename: str = "session.jsonl") -> None:
        """保存到 JSONL 文件
        
        Args:
            dir_path: 目录路径 (channel 目录)
            filename: 文件名 (默认 session.jsonl)
        """
        dir_path.mkdir(parents=True, exist_ok=True)
        file_path = dir_path / filename
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(self.to_dict(), ensure_ascii=False) + "\n")

    @staticmethod
    def load_from_file(file_path: Path) -> "Session | None":
        """从 JSONL 文件加载"""
        if not file_path.exists():
            return None
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.loads(f.readline())
            return Session.from_dict(data)
        except (json.JSONDecodeError, KeyError):
            return None
