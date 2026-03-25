"""Channels module for various platform integrations."""
from .base import Channel, ChannelType, InboundMessage, OutboundMessage
from .console import ConsoleChannel
from .telegram import TelegramChannel
from .feishu import FeishuChannel, FeishuWebHookChannel
from .feishu_ws import FeishuWSChannel
from .webhook import WebhookChannel
from .manager import ChannelManager

__all__ = [
    # Base
    "Channel",
    "ChannelType",
    "InboundMessage",
    "OutboundMessage",
    # Channels
    "ConsoleChannel",
    "TelegramChannel",
    "FeishuChannel",
    "FeishuWebHookChannel",
    "FeishuWSChannel",
    "WebhookChannel",
    # Manager
    "ChannelManager",
]
