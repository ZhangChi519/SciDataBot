"""Skill model - represents a skill loaded from SKILL.md"""

import os
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class SkillMetadata:
    """Skill metadata from YAML frontmatter"""
    name: str = ""
    description: str = ""
    homepage: str = ""
    emoji: str = ""
    requires: dict = field(default_factory=dict)
    always: bool = False


@dataclass
class Skill:
    """
    Skill representation - loaded from SKILL.md files

    OpenClaw style skills have:
    - SKILL.md with YAML frontmatter + markdown content
    - name, description, when to use, commands
    """
    name: str
    description: str
    content: str  # Full markdown content
    metadata: SkillMetadata = field(default_factory=SkillMetadata)
    path: Path = None
    enabled: bool = True

    @classmethod
    def from_file(cls, skill_path: Path) -> "Skill":
        """Load skill from SKILL.md file"""
        with open(skill_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Parse YAML frontmatter
        metadata = SkillMetadata()
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = parts[1]
                try:
                    data = yaml.safe_load(frontmatter)
                    if data:
                        metadata.name = data.get("name", "")
                        metadata.description = data.get("description", "")
                        metadata.homepage = data.get("homepage", "")
                        # Parse metadata - 支持 openclaw 和 scidatabot 格式
                        meta = data.get("metadata", {})
                        if meta:
                            # 尝试 scidatabot 格式
                            sc_meta = meta.get("scidatabot", {})
                            # 或者回退到 openclaw 格式
                            if not sc_meta:
                                sc_meta = meta.get("openclaw", {})
                            metadata.emoji = sc_meta.get("emoji", "")
                            metadata.requires = sc_meta.get("requires", {})
                            metadata.always = sc_meta.get("always", False)
                except Exception:
                    pass

        return cls(
            name=metadata.name or skill_path.parent.name,
            description=metadata.description,
            content=content,
            metadata=metadata,
            path=skill_path,
        )

    def to_dict(self) -> dict:
        """Convert to dict for serialization"""
        return {
            "name": self.name,
            "description": self.description,
            "path": str(self.path),
            "enabled": self.enabled,
            "emoji": self.metadata.emoji,
        }
