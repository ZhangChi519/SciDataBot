"""进程管理模块 - 移植自 OpenClaw Supervisor

功能:
- 进程生命周期管理
- 超时控制 (overall-timeout, no-output-timeout)
- 输出捕获
- Kill tree (进程树终止)
- 重启恢复
- Scope 隔离
"""

import asyncio
import signal
import os
import uuid
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional
from loguru import logger


class TerminationReason(Enum):
    """终止原因"""
    NORMAL = "normal"
    MANUAL_CANCEL = "manual-cancel"
    OVERALL_TIMEOUT = "overall-timeout"
    NO_OUTPUT_TIMEOUT = "no-output-timeout"
    ERROR = "error"
    RESTART = "restart"


class RunState(Enum):
    """运行状态"""
    STARTING = "starting"
    RUNNING = "running"
    EXITING = "exiting"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class SpawnInput:
    """进程Spawn输入参数"""
    command: str
    cwd: Optional[str] = None
    env: Optional[dict] = None
    timeout_ms: Optional[float] = None
    no_output_timeout_ms: Optional[float] = None
    capture_output: bool = True
    shell: bool = True
    scope_key: Optional[str] = None
    session_id: Optional[str] = None
    backend_id: Optional[str] = None
    run_id: Optional[str] = None
    replace_existing_scope: bool = False
    on_output: Optional[Callable[[str], None]] = None
    on_completion: Optional[Callable[[dict], None]] = None


@dataclass
class ManagedRun:
    """管理的运行实例"""
    run_id: str
    process: Optional[asyncio.subprocess.Process] = None
    state: RunState = RunState.STARTING
    stdout: str = ""
    stderr: str = ""
    start_time: float = field(default_factory=time.time)
    last_output_time: float = field(default_factory=time.time)
    exit_code: Optional[int] = None
    termination_reason: TerminationReason = TerminationReason.NORMAL

    # 控制
    cancel_callback: Optional[Callable] = None


@dataclass
class RunRecord:
    """运行记录"""
    run_id: str
    session_id: Optional[str] = None
    backend_id: Optional[str] = None
    scope_key: Optional[str] = None
    state: RunState = RunState.STARTING
    command: str = ""
    started_at_ms: float = 0
    last_output_at_ms: float = 0
    created_at_ms: float = 0
    updated_at_ms: float = 0
    termination_reason: TerminationReason = TerminationReason.NORMAL
    exit_code: Optional[int] = None


def clamp_timeout(value: Optional[float]) -> Optional[float]:
    """验证并规范化超时值"""
    if value is None or not isinstance(value, (int, float)) or value <= 0:
        return None
    return max(1, int(value / 1000))  # 转换为秒


class ProcessSupervisor:
    """
    进程监管者 - 企业级进程管理

    特性:
    - 超时控制 (overall, no-output)
    - 输出捕获
    - Kill tree
    - Scope 隔离
    - 重启恢复
    """

    def __init__(self):
        self._runs: dict[str, ManagedRun] = {}
        self._records: dict[str, RunRecord] = {}
        self._scopes: dict[str, set[str]] = {}  # scope_key -> run_ids
        self._lock = asyncio.Lock()

    async def spawn(self, input: SpawnInput) -> ManagedRun:
        """Spawn 一个新进程"""
        run_id = input.run_id or str(uuid.uuid4())

        # 取消同 scope 的旧任务
        if input.scope_key and input.replace_existing_scope:
            await self.cancel_scope(input.scope_key)

        # 创建运行记录
        record = RunRecord(
            run_id=run_id,
            session_id=input.session_id,
            backend_id=input.backend_id,
            scope_key=input.scope_key,
            state=RunState.STARTING,
            command=input.command,
            started_at_ms=time.time() * 1000,
            last_output_at_ms=time.time() * 1000,
            created_at_ms=time.time() * 1000,
            updated_at_ms=time.time() * 1000,
        )

        # 注册 scope
        if input.scope_key:
            if input.scope_key not in self._scopes:
                self._scopes[input.scope_key] = set()
            self._scopes[input.scope_key].add(run_id)

        self._records[run_id] = record

        # 创建 ManagedRun
        run = ManagedRun(
            run_id=run_id,
            state=RunState.STARTING,
        )
        self._runs[run_id] = run

        # 执行进程
        await self._execute_run(run, input, record)

        return run

    async def _execute_run(self, run: ManagedRun, input: SpawnInput, record: RunRecord):
        """执行进程"""
        timeout = clamp_timeout(input.timeout_ms)
        no_output_timeout = clamp_timeout(input.no_output_timeout_ms)

        async def cancel(reason: TerminationReason):
            run.termination_reason = reason
            if run.process and run.process.returncode is None:
                try:
                    run.process.terminate()
                    await asyncio.sleep(0.5)
                    if run.process.returncode is None:
                        run.process.kill()
                except ProcessLookupError:
                    pass

        run.cancel_callback = cancel

        try:
            # 启动进程
            run.state = RunState.RUNNING
            record.state = RunState.RUNNING

            process = await asyncio.create_subprocess_shell(
                input.command,
                stdout=asyncio.subprocess.PIPE if input.capture_output else None,
                stderr=asyncio.subprocess.PIPE if input.capture_output else None,
                cwd=input.cwd,
                env=input.env or os.environ.copy(),
            )
            run.process = process

            # 设置超时定时器
            timeout_task = None
            no_output_task = None

            if timeout:
                async def overall_timeout():
                    await asyncio.sleep(timeout)
                    await cancel(TerminationReason.OVERALL_TIMEOUT)
                timeout_task = asyncio.create_task(overall_timeout())

            if no_output_timeout:
                async def no_output_timer():
                    await asyncio.sleep(no_output_timeout)
                    await cancel(TerminationReason.NO_OUTPUT_TIMEOUT)
                no_output_task = asyncio.create_task(no_output_timer())

            # 读取输出
            async def read_stream(stream, is_stdout=True):
                nonlocal run
                while True:
                    try:
                        line = await asyncio.wait_for(stream.readline(), timeout=1)
                        if not line:
                            break
                        text = line.decode('utf-8', errors='replace')
                        if is_stdout:
                            run.stdout += text
                        else:
                            run.stderr += text
                        run.last_output_time = time.time()
                        record.last_output_at_ms = time.time() * 1000

                        # 重置 no-output 定时器
                        if no_output_task and not no_output_task.done():
                            no_output_task.cancel()
                            no_output_task = asyncio.create_task(no_output_timer())

                        # 回调
                        if input.on_output:
                            input.on_output(text)
                    except asyncio.TimeoutError:
                        continue
                    except Exception:
                        break

            # 并行读取 stdout 和 stderr
            tasks = []
            if process.stdout:
                tasks.append(read_stream(process.stdout, True))
            if process.stderr:
                tasks.append(read_stream(process.stderr, False))

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

            # 等待进程结束
            exit_code = await process.wait()

            # 取消定时器
            if timeout_task:
                timeout_task.cancel()
            if no_output_task:
                no_output_task.cancel()

            run.exit_code = exit_code
            run.state = RunState.COMPLETED if exit_code == 0 else RunState.FAILED
            record.state = run.state
            record.exit_code = exit_code
            record.termination_reason = TerminationReason.NORMAL

            if input.on_completion:
                input.on_completion({
                    "run_id": run_id,
                    "exit_code": exit_code,
                    "stdout": run.stdout,
                    "stderr": run.stderr,
                })

            logger.info(f"Process {run_id} completed with code {exit_code}")

        except asyncio.CancelledError:
            run.state = RunState.EXITING
            record.state = RunState.EXITING
            await cancel(TerminationReason.MANUAL_CANCEL)
            raise
        except Exception as e:
            logger.error(f"Process {run_id} failed: {e}")
            run.state = RunState.FAILED
            record.state = RunState.FAILED
            record.termination_reason = TerminationReason.ERROR
            run.stderr += f"\nError: {str(e)}"

    async def cancel(self, run_id: str, reason: TerminationReason = TerminationReason.MANUAL_CANCEL):
        """取消指定运行"""
        run = self._runs.get(run_id)
        if run and run.cancel_callback:
            await run.cancel_callback(reason)

    async def cancel_scope(self, scope_key: str, reason: TerminationReason = TerminationReason.MANUAL_CANCEL):
        """取消指定 scope 的所有运行"""
        run_ids = self._scopes.get(scope_key, set()).copy()
        for run_id in run_ids:
            await self.cancel(run_id, reason)

    def get_run(self, run_id: str) -> Optional[ManagedRun]:
        """获取运行实例"""
        return self._runs.get(run_id)

    def get_record(self, run_id: str) -> Optional[RunRecord]:
        """获取运行记录"""
        return self._records.get(run_id)

    def list_runs(self, scope_key: Optional[str] = None) -> list[RunRecord]:
        """列出运行记录"""
        if scope_key:
            run_ids = self._scopes.get(scope_key, set())
            return [self._records[rid] for rid in run_ids if rid in self._records]
        return list(self._records.values())

    async def kill_tree(self, pid: int):
        """Kill 进程树"""
        try:
            # 使用 kill 命令杀进程树
            proc = await asyncio.create_subprocess_shell(
                f"pkill -P {pid}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
        except Exception as e:
            logger.warning(f"Failed to kill process tree: {e}")

        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


# 全局 Supervisor 实例
_supervisor: Optional[ProcessSupervisor] = None


def get_supervisor() -> ProcessSupervisor:
    """获取全局 Supervisor"""
    global _supervisor
    if _supervisor is None:
        _supervisor = ProcessSupervisor()
    return _supervisor
