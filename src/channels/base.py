"""Channel base classes and interfaces."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from enum import Enum


class ChannelType(Enum):
    """Channel types."""
    CONSOLE = "console"
    TELEGRAM = "telegram"
    FEISHU = "feishu"
    LINE = "line"
    WEB = "web"
    WEBHOOK = "webhook"
    SLACK = "slack"
    DISCORD = "discord"


@dataclass
class InboundMessage:
    """Inbound message from a channel."""

    channel: str
    chat_id: str
    user_id: str
    content: str
    message_id: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class OutboundMessage:
    """Outbound message to a channel."""

    chat_id: str
    content: str
    reply_to: Optional[str] = None  # message_id to reply to
    metadata: dict = field(default_factory=dict)


class Channel(ABC):
    """Base class for channel implementations."""

    def __init__(self, channel_type: ChannelType, config: dict):
        """Initialize channel.

        Args:
            channel_type: Type of channel
            config: Channel configuration
        """
        self.channel_type = channel_type
        self.config = config
        self._message_handler: Optional[Callable] = None

    def set_message_handler(self, handler: Callable[[InboundMessage], Any]):
        """Set handler for incoming messages."""
        self._message_handler = handler

    @abstractmethod
    async def start(self) -> None:
        """Start the channel (connect/listen)."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the channel (disconnect)."""
        pass

    @abstractmethod
    async def send_message(self, message: OutboundMessage) -> str:
        """Send a message to the channel.

        Returns:
            Message ID of sent message.
        """
        pass

    async def handle_inbound(self, message: InboundMessage) -> Any:
        """Handle inbound message with registered handler."""
        if self._message_handler:
            return await self._message_handler(message)
        raise NotImplementedError("No message handler registered")

    @property
    def channel_id(self) -> str:
        """Get unique channel identifier."""
        return self.channel_type.value
