"""Skill loader - load and manage skills from SKILL.md files"""

import os
import shutil
from pathlib import Path
from typing import List, Optional, Dict

from loguru import logger

from .loader import Skill, SkillMetadata


class SkillLoader:
    """
    Skill loader - manages skill installation and loading

    Skills are loaded from:
    - Built-in skills: src/skills/builtin/
    - User skills: ~/.scidatabot/skills/
    - External skills: can be installed via CLI
    """

    def __init__(self, skills_dir: Optional[Path] = None):
        """Initialize skill loader"""
        # Default skills directory
        if skills_dir:
            self.skills_dir = skills_dir
        else:
            # User skills directory
            self.skills_dir = Path.home() / ".scidatabot" / "skills"

        self.skills_dir.mkdir(parents=True, exist_ok=True)

        # Built-in skills directory
        self.builtin_dir = Path(__file__).parent / "builtin"
        if not self.builtin_dir.exists():
            self.builtin_dir = Path(__file__).parent / "skills"

        # Loaded skills cache
        self._skills: Dict[str, Skill] = {}
        self._loaded = False

    def load_all(self) -> Dict[str, Skill]:
        """Load all skills (builtin + user installed)"""
        if self._loaded:
            return self._skills

        self._skills = {}

        # Load built-in skills
        if self.builtin_dir.exists():
            self._load_from_dir(self.builtin_dir, is_builtin=True)

        # Load user skills
        self._load_from_dir(self.skills_dir, is_builtin=False)

        self._loaded = True
        logger.info(f"Loaded {len(self._skills)} skills")
        return self._skills

    def _load_from_dir(self, skills_path: Path, is_builtin: bool = False):
        """Load skills from a directory"""
        if not skills_path.exists():
            return

        for item in skills_path.iterdir():
            if item.is_dir():
                skill_file = item / "SKILL.md"
                if skill_file.exists():
                    try:
                        skill = Skill.from_file(skill_file)
                        skill.path = skill_file
                        # Mark as builtin if from builtin dir
                        if is_builtin:
                            skill.metadata.name = f"builtin:{skill.name}"
                        self._skills[skill.name] = skill
                        logger.debug(f"Loaded skill: {skill.name}")
                    except Exception as e:
                        logger.warning(f"Failed to load skill {item.name}: {e}")

    def get(self, name: str) -> Optional[Skill]:
        """Get a skill by name"""
        if not self._loaded:
            self.load_all()

        # Try exact match
        if name in self._skills:
            return self._skills[name]

        # Try with builtin: prefix
        if name.startswith("builtin:"):
            key = name.replace("builtin:", "")
            if key in self._skills:
                return self._skills[key]

        return None

    def list(self) -> List[Skill]:
        """List all available skills"""
        if not self._loaded:
            self.load_all()
        return list(self._skills.values())

    def install(self, skill_path: Path) -> Skill:
        """
        Install a skill from a local directory

        Args:
            skill_path: Path to skill directory containing SKILL.md

        Returns:
            The installed skill
        """
        skill_file = skill_path / "SKILL.md"
        if not skill_file.exists():
            raise ValueError(f"SKILL.md not found in {skill_path}")

        # Load the skill
        skill = Skill.from_file(skill_file)

        # Copy to user skills directory
        dest_dir = self.skills_dir / skill.name
        if dest_dir.exists():
            logger.warning(f"Skill {skill.name} already exists, overwriting")

        # Copy directory
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
        shutil.copytree(skill_path, dest_dir)

        # Reload skills
        self._loaded = False
        self.load_all()

        logger.info(f"Installed skill: {skill.name}")
        return self.get(skill.name)

    def uninstall(self, name: str) -> bool:
        """Uninstall a user skill (not builtin)"""
        skill = self.get(name)
        if not skill:
            logger.warning(f"Skill not found: {name}")
            return False

        # Check if builtin
        if name.startswith("builtin:") or str(skill.path).startswith(str(self.builtin_dir)):
            logger.warning(f"Cannot uninstall builtin skill: {name}")
            return False

        # Remove from filesystem
        skill_dir = skill.path.parent
        if skill_dir.exists():
            shutil.rmtree(skill_dir)

        # Reload
        self._loaded = False
        self.load_all()

        logger.info(f"Uninstalled skill: {name}")
        return True

    def get_skill_prompt(self, name: str) -> Optional[str]:
        """Get the full prompt content for a skill"""
        skill = self.get(name)
        if skill:
            return skill.content
        return None

    def build_skills_summary(self) -> str:
        """生成所有 skills 的摘要（供 Agent 使用）"""
        skills = self.list()
        if not skills:
            return "暂无可用 skills"
        
        lines = []
        for s in skills:
            emoji = s.metadata.emoji or "📦"
            always_mark = " (常用)" if s.metadata.always else ""
            lines.append(f"- {emoji} **{s.name}**: {s.description}{always_mark}")
        
        return "\n".join(lines)

    def get_always_skills(self) -> List[str]:
        """获取始终加载的 skills"""
        result = []
        for s in self.list():
            if s.metadata.always:
                result.append(s.name)
        return result

    def load_skills_for_context(self, names: List[str]) -> str:
        """加载指定 skills 的完整内容"""
        parts = []
        for name in names:
            content = self.get_skill_prompt(name)
            if content:
                # 移除 frontmatter
                if content.startswith("---"):
                    parts_content = content.split("---", 2)
                    if len(parts_content) >= 3:
                        content = parts_content[2].strip()
                parts.append(f"### Skill: {name}\n\n{content}")
        
        return "\n\n---\n\n".join(parts) if parts else ""


# Global skill loader instance
_loader: Optional[SkillLoader] = None


def get_skill_loader() -> SkillLoader:
    """Get global skill loader instance"""
    global _loader
    if _loader is None:
        _loader = SkillLoader()
    return _loader
