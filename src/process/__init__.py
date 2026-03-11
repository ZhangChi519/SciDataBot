"""
进程管理模块

包含以下子模块:
- supervisor: 进程监管 (超时, kill-tree, scope 隔离)
- batch: 批量处理 (并行, 限流, 重试)
- command_queue: 命令队列 (优先级, 速率限制)
- guardrails: 安全护栏 (命令拦截, 路径限制)
- stream: 流式输出 (实时事件)
"""

from .supervisor import (
    ProcessSupervisor,
    ManagedRun,
    RunRecord,
    RunState,
    SpawnInput,
    TerminationReason,
    get_supervisor,
)

from .batch import (
    BatchProcessor,
    BatchStrategy,
    BatchItem,
    BatchResult,
    RetryPolicy,
)

from .command_queue import (
    CommandQueue,
    QueuePriority,
    QueuedCommand,
    get_command_queue,
)

from .guardrails import (
    Guardrails,
    GuardrailAction,
    GuardrailResult,
    get_guardrails,
)

from .stream import (
    StreamOutput,
    StreamProcessor,
    StreamEvent,
    StreamEventType,
    get_stream_output,
)

__all__ = [
    # Supervisor
    "ProcessSupervisor",
    "ManagedRun",
    "RunRecord",
    "RunState",
    "SpawnInput",
    "TerminationReason",
    "get_supervisor",
    # Batch
    "BatchProcessor",
    "BatchStrategy",
    "BatchItem",
    "BatchResult",
    "RetryPolicy",
    # Command Queue
    "CommandQueue",
    "QueuePriority",
    "QueuedCommand",
    "get_command_queue",
    # Guardrails
    "Guardrails",
    "GuardrailAction",
    "GuardrailResult",
    "get_guardrails",
    # Stream
    "StreamOutput",
    "StreamProcessor",
    "StreamEvent",
    "StreamEventType",
    "get_stream_output",
]
