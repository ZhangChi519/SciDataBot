"""Heartbeat module for monitoring and health checks."""
import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from enum import Enum

from loguru import logger


class HeartbeatStatus(Enum):
    """Heartbeat status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    STOPPED = "stopped"


@dataclass
class Heartbeat:
    """Represents a single heartbeat."""

    timestamp: float
    status: HeartbeatStatus
    data: Dict[str, Any] = field(default_factory=dict)


class HeartbeatMonitor:
    """Monitor for tracking system health."""

    def __init__(self, interval: float = 60.0):
        """Initialize heartbeat monitor.

        Args:
            interval: Heartbeat check interval in seconds
        """
        self.interval = interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._handlers: Dict[str, Callable] = {}
        self._history: List[Heartbeat] = []
        self._max_history = 100

    def register_handler(self, name: str, handler: Callable[[], Any]) -> None:
        """Register a health check handler.

        Args:
            name: Handler name
            handler: Async function that returns status dict
        """
        self._handlers[name] = handler

    def unregister_handler(self, name: str) -> bool:
        """Unregister a handler."""
        if name in self._handlers:
            del self._handlers[name]
            return True
        return False

    async def start(self) -> None:
        """Start the heartbeat monitor."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("Heartbeat monitor started")

    async def stop(self) -> None:
        """Stop the heartbeat monitor."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Heartbeat monitor stopped")

    async def _run(self) -> None:
        """Main heartbeat loop."""
        while self._running:
            try:
                await self._check()
            except Exception as e:
                logger.error(f"Error in heartbeat check: {e}")

            await asyncio.sleep(self.interval)

    async def _check(self) -> None:
        """Perform health check."""
        status = HeartbeatStatus.HEALTHY
        data = {}
        issues = []

        for name, handler in self._handlers.items():
            try:
                result = handler()
                if asyncio.iscoroutine(result):
                    result = await result

                if isinstance(result, dict):
                    if result.get("status") == "unhealthy":
                        status = HeartbeatStatus.UNHEALTHY
                        issues.append(f"{name}: {result.get('message', 'unhealthy')}")

                    data[name] = result.get("data", result)
                else:
                    data[name] = result

            except Exception as e:
                status = HeartbeatStatus.DEGRADED
                issues.append(f"{name}: {str(e)}")
                logger.warning(f"Health check failed for {name}: {e}")

        # Record heartbeat
        heartbeat = Heartbeat(
            timestamp=time.time(),
            status=status,
            data=data,
        )

        self._history.append(heartbeat)

        # Trim history
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        # Log status
        if status == HeartbeatStatus.HEALTHY:
            logger.debug("System healthy")
        else:
            logger.warning(f"System status: {status.value} - {', '.join(issues)}")

    async def check_now(self) -> Heartbeat:
        """Trigger an immediate health check."""
        await self._check()
        return self._history[-1] if self._history else Heartbeat(
            timestamp=time.time(),
            status=HeartbeatStatus.STOPPED,
        )

    def get_status(self) -> HeartbeatStatus:
        """Get current status."""
        if not self._history:
            return HeartbeatStatus.STOPPED

        return self._history[-1].status

    def get_history(self, limit: int = 10) -> List[Heartbeat]:
        """Get heartbeat history."""
        return self._history[-limit:]

    def is_healthy(self) -> bool:
        """Check if system is healthy."""
        if not self._history:
            return False
        return self._history[-1].status == HeartbeatStatus.HEALTHY


# Predefined health check handlers


async def check_system_resources() -> Dict[str, Any]:
    """Check system resources."""
    import psutil

    return {
        "cpu_percent": psutil.cpu_percent(),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_percent": psutil.disk_usage("/").percent,
    }


async def check_database_connection() -> Dict[str, Any]:
    """Check database connection."""
    # Placeholder - would check actual database
    return {
        "status": "healthy",
        "data": {"connected": True},
    }


async def check_llm_provider() -> Dict[str, Any]:
    """Check LLM provider availability."""
    # Placeholder - would check actual provider
    return {
        "status": "healthy",
        "data": {"available": True},
    }


# Global heartbeat monitor
_monitor: Optional[HeartbeatMonitor] = None


def get_heartbeat_monitor() -> HeartbeatMonitor:
    """Get global heartbeat monitor."""
    global _monitor
    if _monitor is None:
        _monitor = HeartbeatMonitor()
    return _monitor
