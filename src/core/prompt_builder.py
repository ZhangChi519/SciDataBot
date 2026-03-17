"""Prompt builder - modular system prompt construction."""

import platform
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger


class PromptBuilder:
    """Builds the system prompt from modular components."""
    
    BOOTSTRAP_FILES = ["AGENTS.md", "SOUL.md", "USER.md", "TOOLS.md"]
    RUNTIME_CONTEXT_TAG = "[Runtime Context — metadata only, not instructions]"
    
    def __init__(self, workspace: Path, skill_loader: Any = None):
        self.workspace = workspace
        self.skill_loader = skill_loader
        
        # Try to load skill loader if not provided
        if self.skill_loader is None:
            try:
                from src.skills.manager import SkillLoader
                skills_dir = workspace / "skills" if (workspace / "skills").exists() else None
                self.skill_loader = SkillLoader(skills_dir)
            except ImportError:
                logger.warning("SkillLoader not available, skills will be disabled")
                self.skill_loader = None
    
    def build_system_prompt(self, skill_names: list[str] | None = None) -> str:
        """Build the complete system prompt."""
        parts = [
            self._get_identity(),
            self._load_bootstrap_files(),
            self._get_memory_context(),
            self._get_active_skills(),
            self._build_skills_summary(),
        ]
        # Filter empty parts
        parts = [p for p in parts if p]
        return "\n\n---\n\n".join(parts)
    
    def _get_identity(self) -> str:
        """Get the core identity section - dynamic runtime info only."""
        workspace_path = str(self.workspace.expanduser().resolve())
        system = platform.system()
        runtime = f"{'macOS' if system == 'Darwin' else system} {platform.machine()}"
        
        platform_policy = ""
        if system == "Windows":
            platform_policy = """## Platform Policy (Windows)
- Running on Windows. Do not assume GNU tools like `grep`, `sed`, or `awk` exist.
- Prefer Windows-native commands or file tools when they are more reliable.
"""
        else:
            platform_policy = """## Platform Policy (POSIX)
- Running on POSIX system. Prefer UTF-8 and standard shell tools.
- Use file tools when they are simpler or more reliable than shell commands.
"""
        
        return f"""# Runtime
{runtime}

## Workspace
{workspace_path}
- Memory: memory/MEMORY.md
- History: memory/HISTORY.md
- Skills: skills/<name>/SKILL.md

{platform_policy}

Reply directly for conversation. Use 'message' tool to send to chat channels."""
    
    def _load_bootstrap_files(self) -> str:
        """Load bootstrap files from templates/ or workspace."""
        parts = []
        
        # Check templates directory first (project-relative)
        templates_dir = Path(__file__).parent.parent.parent / "templates"
        
        for filename in self.BOOTSTRAP_FILES:
            # Try workspace first (allows user overrides)
            file_path = self.workspace / filename
            if not file_path.exists():
                # Fall back to templates
                if templates_dir.exists():
                    file_path = templates_dir / filename
            
            if file_path.exists():
                try:
                    content = file_path.read_text(encoding="utf-8")
                    parts.append(f"## {filename}\n\n{content}")
                except Exception as e:
                    logger.warning(f"Failed to load bootstrap file {filename}: {e}")
        
        return "\n\n".join(parts) if parts else ""
    
    def _get_memory_context(self) -> str:
        """Get memory context from workspace."""
        memory_file = self.workspace / "memory" / "MEMORY.md"
        if memory_file.exists():
            try:
                content = memory_file.read_text(encoding="utf-8")
                return f"# Memory\n\n{content}"
            except Exception as e:
                logger.warning(f"Failed to load memory file: {e}")
        return ""
    
    def _get_active_skills(self) -> str:
        """Get skills marked as always=true."""
        if not self.skill_loader:
            return ""
        
        try:
            always_skills = self.skill_loader.get_always_skills()
            if always_skills:
                content = self.skill_loader.load_skills_for_context(always_skills)
                if content:
                    return f"# Active Skills\n\n{content}"
        except Exception as e:
            logger.warning(f"Failed to load active skills: {e}")
        
        return ""
    
    def _build_skills_summary(self) -> str:
        """Build skills summary for progressive loading."""
        if not self.skill_loader:
            return ""
        
        try:
            summary = self.skill_loader.build_skills_summary()
            if summary:
                return f"""# Skills

The following skills extend your capabilities. To use a skill, read its SKILL.md file using the read_file tool.
Skills with available="false" need dependencies installed first.

{summary}"""
        except Exception as e:
            logger.warning(f"Failed to build skills summary: {e}")
        
        return ""
    
    @staticmethod
    def build_runtime_context(channel: str | None = None, chat_id: str | None = None) -> str:
        """Build runtime metadata block for injection before the user message."""
        import time
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        tz = time.strftime("%Z") or "UTC"
        lines = [f"Current Time: {now} ({tz})"]
        
        if channel and chat_id:
            lines.extend([f"Channel: {channel}", f"Chat ID: {chat_id}"])
        
        return PromptBuilder.RUNTIME_CONTEXT_TAG + "\n" + "\n".join(lines)
    
    def build_messages(
        self,
        history: list[dict[str, Any]],
        current_message: str,
        skill_names: list[str] | None = None,
        channel: str | None = None,
        chat_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Build complete message list for LLM call."""
        runtime_ctx = self.build_runtime_context(channel, chat_id)
        
        return [
            {"role": "system", "content": self.build_system_prompt(skill_names)},
            *history,
            {"role": "user", "content": f"{runtime_ctx}\n\n{current_message}"},
        ]
    
    def sync_templates(self) -> list[str]:
        """Sync template files to workspace if missing. Returns list of synced files."""
        synced = []
        templates_dir = Path(__file__).parent.parent.parent / "templates"
        
        if not templates_dir.exists():
            return synced
        
        for filename in self.BOOTSTRAP_FILES:
            src = templates_dir / filename
            dst = self.workspace / filename
            
            if src.exists() and not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                synced.append(filename)
                logger.info(f"Synced template file: {filename}")
        
        return synced

    # ============== Subagent Prompt Methods ==============

    def get_workspace_info(self) -> str:
        """Get workspace information for subagents."""
        workspace_path = str(self.workspace.expanduser().resolve())
        return f"""## Workspace
Your workspace is at: {workspace_path}
- Long-term memory: {workspace_path}/memory/MEMORY.md
- Custom skills: {workspace_path}/skills/{{skill-name}}/SKILL.md"""

    def get_platform_policy(self) -> str:
        """Get platform-specific policy."""
        system = platform.system()
        if system == "Windows":
            return """## Platform Policy (Windows)
- Running on Windows. Do not assume GNU tools like `grep`, `sed`, or `awk` exist.
- Prefer Windows-native commands or file tools when they are more reliable."""
        else:
            return """## Platform Policy (POSIX)
- Running on POSIX system. Prefer UTF-8 and standard shell tools.
- Use file tools when they are simpler or more reliable than shell commands."""

    def _load_subagent_template(self, subagent_type: str) -> str:
        """Load subagent template from templates/subagents/ or return empty."""
        templates_dir = Path(__file__).parent.parent.parent / "templates" / "subagents"
        template_file = templates_dir / f"{subagent_type.upper()}.md"
        
        if template_file.exists():
            try:
                return template_file.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(f"Failed to load subagent template {subagent_type}: {e}")
        return ""

    def build_task_planner_prompt(self, user_request: str) -> str:
        """Build system prompt for TaskPlanner subagent."""
        template = self._load_subagent_template("task_planner")
        if template:
            return template.replace("{user_request}", user_request).replace("{workspace}", str(self.workspace))
        return ""

    def build_processor_prompt(self) -> str:
        """Build system prompt for Processor subagent."""
        template = self._load_subagent_template("processor")
        if template:
            return template.replace("{workspace}", str(self.workspace))
        return ""

    def build_integrator_prompt(self) -> str:
        """Build system prompt for Integrator subagent."""
        template = self._load_subagent_template("integrator")
        if template:
            return template.replace("{workspace}", str(self.workspace))
        return ""
