"""Message Bus for async message passing between components."""
import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from enum import Enum
import time
import uuid


class MessagePriority(Enum):
    """Message priority levels."""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class Message:
    """Represents a message in the bus."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: str = ""
    payload: Any = None
    sender: str = ""
    receiver: str = ""
    priority: MessagePriority = MessagePriority.NORMAL
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    reply_to: Optional[str] = None  # Message ID to reply to

    def __lt__(self, other):
        """Compare by priority for priority queue."""
        if not isinstance(other, Message):
            return NotImplemented
        return self.priority.value > other.priority.value  # Higher priority first


class MessageBus:
    """Async message bus for publish-subscribe pattern."""

    def __init__(self, max_size: int = 1000):
        """Initialize message bus.

        Args:
            max_size: Maximum queue size per subscriber
        """
        self.max_size = max_size
        self._queues: Dict[str, asyncio.PriorityQueue] = {}
        self._handlers: Dict[str, List[Callable]] = {}
        self._subscribers: Dict[str, str] = {}  # subscriber_id -> queue_name
        self._lock = asyncio.Lock()

    async def subscribe(
        self,
        queue_name: str,
        handler: Optional[Callable] = None,
        subscriber_id: Optional[str] = None,
    ) -> str:
        """Subscribe to a message queue.

        Args:
            queue_name: Name of the queue to subscribe to
            handler: Optional async handler function
            subscriber_id: Optional subscriber ID

        Returns:
            Subscriber ID
        """
        async with self._lock:
            if queue_name not in self._queues:
                self._queues[queue_name] = asyncio.PriorityQueue(maxsize=self.max_size)

            if handler:
                if queue_name not in self._handlers:
                    self._handlers[queue_name] = []
                self._handlers[queue_name].append(handler)

            sub_id = subscriber_id or f"{queue_name}:{uuid.uuid4().hex[:8]}"
            self._subscribers[sub_id] = queue_name

            return sub_id

    async def unsubscribe(self, subscriber_id: str) -> bool:
        """Unsubscribe from a queue."""
        async with self._lock:
            if subscriber_id in self._subscribers:
                queue_name = self._subscribers.pop(subscriber_id)
                if queue_name in self._handlers:
                    # Remove all handlers for this subscriber would need more tracking
                    pass
                return True
            return False

    async def publish(
        self,
        queue_name: str,
        message: Message,
    ) -> None:
        """Publish a message to a queue.

        Args:
            queue_name: Name of the queue
            message: Message to publish
        """
        async with self._lock:
            if queue_name not in self._queues:
                self._queues[queue_name] = asyncio.PriorityQueue(maxsize=self.max_size)

        await self._queues[queue_name].put(message)

    async def receive(
        self,
        subscriber_id: str,
        timeout: Optional[float] = None,
    ) -> Optional[Message]:
        """Receive a message from subscribed queue.

        Args:
            subscriber_id: Subscriber ID
            timeout: Optional timeout in seconds

        Returns:
            Message or None if timeout
        """
        async with self._lock:
            queue_name = self._subscribers.get(subscriber_id)
            if not queue_name or queue_name not in self._queues:
                return None

            queue = self._queues[queue_name]

        try:
            message = await asyncio.wait_for(queue.get(), timeout=timeout)
            return message
        except asyncio.TimeoutError:
            return None

    async def receive_all(
        self,
        subscriber_id: str,
        max_messages: int = 10,
        timeout: float = 1.0,
    ) -> List[Message]:
        """Receive multiple messages.

        Args:
            subscriber_id: Subscriber ID
            max_messages: Maximum messages to receive
            timeout: Timeout per message

        Returns:
            List of messages
        """
        messages = []

        for _ in range(max_messages):
            message = await self.receive(subscriber_id, timeout=timeout)
            if message is None:
                break
            messages.append(message)

        return messages

    async def handle_messages(
        self,
        subscriber_id: str,
        handler: Callable[[Message], Any],
    ) -> None:
        """Continuously handle messages with a handler.

        Args:
            subscriber_id: Subscriber ID
            handler: Async function to handle each message
        """
        while subscriber_id in self._subscribers:
            message = await self.receive(subscriber_id, timeout=1.0)
            if message:
                try:
                    result = handler(message)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    print(f"Error handling message: {e}")

    def get_queue_size(self, queue_name: str) -> int:
        """Get current size of a queue."""
        if queue_name in self._queues:
            return self._queues[queue_name].qsize()
        return 0

    def list_subscribers(self) -> Dict[str, str]:
        """List all subscribers."""
        return self._subscribers.copy()

    async def clear_queue(self, queue_name: str) -> int:
        """Clear all messages in a queue.

        Returns:
            Number of messages cleared
        """
        async with self._lock:
            if queue_name not in self._queues:
                return 0

            count = 0
            while not self._queues[queue_name].empty():
                try:
                    self._queues[queue_name].get_nowait()
                    count += 1
                except asyncio.QueueEmpty:
                    break

            return count


# Global message bus instance
_global_bus: Optional[MessageBus] = None


def get_message_bus() -> MessageBus:
    """Get the global message bus instance."""
    global _global_bus
    if _global_bus is None:
        _global_bus = MessageBus()
    return _global_bus


def set_message_bus(bus: MessageBus) -> None:
    """Set the global message bus instance."""
    global _global_bus
    _global_bus = bus
