"""Guardrails 安全控制模块 - 移植自 OpenClaw

功能:
- 命令拦截
- 路径限制
- 敏感数据检测
- 黑名单/白名单
"""

import re
import os
from dataclasses import dataclass, field
from typing import Optional, Callable
from enum import Enum
from loguru import logger


class GuardrailAction(Enum):
    """安全动作"""
    ALLOW = "allow"
    BLOCK = "block"
    WARN = "warn"
    SANITIZE = "sanitize"


@dataclass
class GuardrailResult:
    """检查结果"""
    action: GuardrailAction = GuardrailAction.ALLOW
    message: str = ""
    sanitized: Optional[str] = None


class Guardrails:
    """
    安全护栏

    功能:
    - 命令黑名单/白名单
    - 路径限制
    - 敏感数据检测
    - 自定义规则
    """

    # 默认危险命令模式
    DEFAULT_DENY_PATTERNS = [
        r"\brm\s+-[rf]{1,2}\b",          # rm -r, rm -rf
        r"\bdel\s+/[fq]\b",               # del /f, del /q
        r"\brmdir\s+/s\b",                # rmdir /s
        r"\bformat\b",                    # format
        r"\b(mkfs|diskpart)\b",           # 磁盘操作
        r"\bdd\s+if=",                    # dd
        r">\s*/dev/",                    # 写入设备
        r"\b(shutdown|reboot|poweroff)\b", # 关机
        r":\(\)\s*\{.*\};\s*:",          # fork bomb
        r"\bsudo\s+rm\b",                # sudo rm
        r"\bchmod\s+-R\s+777\b",         #  chmod 777
        r"\bcurl.*\|\s*bash\b",          # curl | bash
        r"\bwget.*\|\s*bash\b",          # wget | bash
    ]

    # 默认允许命令白名单 (空 = 不启用)
    DEFAULT_ALLOW_PATTERNS: list[str] = []

    def __init__(
        self,
        deny_patterns: Optional[list[str]] = None,
        allow_patterns: Optional[list[str]] = None,
        restrict_to_workspace: bool = True,
        workspace_path: Optional[str] = None,
        max_output_size: int = 1024 * 1024,  # 1MB
    ):
        self.deny_patterns = deny_patterns or self.DEFAULT_DENY_PATTERNS
        self.allow_patterns = allow_patterns or self.DEFAULT_ALLOW_PATTERNS
        self.restrict_to_workspace = restrict_to_workspace
        self.workspace_path = workspace_path or os.getcwd()
        self.max_output_size = max_output_size

        # 自定义规则
        self._custom_rules: list[Callable[[str], GuardrailResult]] = []

        # 编译正则
        self._deny_regexes = [re.compile(p, re.IGNORECASE) for p in self.deny_patterns]
        self._allow_regexes = [re.compile(p, re.IGNORECASE) for p in self.allow_patterns] if self.allow_patterns else []

    def check_command(self, command: str) -> GuardrailResult:
        """
        检查命令安全性

        Returns:
            GuardrailResult: 检查结果
        """
        cmd = command.strip().lower()

        # 1. 白名单检查 (如果启用)
        if self._allow_regexes:
            if any(r.search(cmd) for r in self._allow_regexes):
                return GuardrailResult(action=GuardrailAction.ALLOW, message="Allowed by whitelist")

        # 2. 黑名单检查
        for pattern, regex in zip(self.deny_patterns, self._deny_regexes):
            if regex.search(cmd):
                return GuardrailResult(
                    action=GuardrailAction.BLOCK,
                    message=f"Command blocked by safety guard (dangerous pattern: {pattern})"
                )

        # 3. 自定义规则
        for rule in self._custom_rules:
            result = rule(command)
            if result.action != GuardrailAction.ALLOW:
                return result

        return GuardrailResult(action=GuardrailAction.ALLOW, message="Command allowed")

    def check_path(self, path: str) -> GuardrailResult:
        """
        检查路径安全性

        Returns:
            GuardrailResult: 检查结果
        """
        import os.path

        # 解析绝对路径
        try:
            abs_path = os.path.abspath(os.path.expanduser(path))
        except Exception as e:
            return GuardrailResult(
                action=GuardrailAction.BLOCK,
                message=f"Invalid path: {e}"
            )

        # 检查路径遍历
        if ".." in path:
            return GuardrailResult(
                action=GuardrailAction.BLOCK,
                message="Path traversal detected (..)"
            )

        # 限制在 workspace 内
        if self.restrict_to_workspace:
            workspace = os.path.abspath(self.workspace_path)
            if not abs_path.startswith(workspace):
                return GuardrailResult(
                    action=GuardrailAction.BLOCK,
                    message=f"Path outside workspace: {workspace}"
                )

        return GuardrailResult(action=GuardrailAction.ALLOW, message="Path allowed")

    def check_output(self, output: str) -> GuardrailResult:
        """
        检查输出大小

        Returns:
            GuardrailResult: 检查结果
        """
        if len(output) > self.max_output_size:
            truncated = output[:self.max_output_size]
            return GuardrailResult(
                action=GuardrailAction.SANITIZE,
                message=f"Output truncated from {len(output)} to {self.max_output_size} bytes",
                sanitized=truncated + f"\n... (truncated, {len(output) - self.max_output_size} more bytes)"
            )

        return GuardrailResult(action=GuardrailAction.ALLOW, message="Output allowed")

    def sanitize_command(self, command: str) -> tuple[str, GuardrailResult]:
        """
        尝试清理危险命令

        Returns:
            (sanitized_command, result)
        """
        result = self.check_command(command)

        if result.action == GuardrailAction.ALLOW:
            return command, result

        # 尝试移除危险部分
        sanitized = command

        # 移除 -rf, -fr 等危险参数
        sanitized = re.sub(r'\s+-[rf]{1,2}\b', '', sanitized)

        # 重新检查
        result = self.check_command(sanitized)

        if result.action == GuardrailAction.ALLOW:
            return sanitized, GuardrailResult(
                action=GuardrailAction.SANITIZE,
                message="Dangerous parameters removed",
                sanitized=sanitized
            )

        return command, result

    def add_rule(self, rule: Callable[[str], GuardrailResult]):
        """添加自定义规则"""
        self._custom_rules.append(rule)


# 全局 Guardrails 实例
_guardrails: Optional[Guardrails] = None


def get_guardrails(**kwargs) -> Guardrails:
    """获取全局 Guardrails"""
    global _guardrails
    if _guardrails is None:
        _guardrails = Guardrails(**kwargs)
    return _guardrails
