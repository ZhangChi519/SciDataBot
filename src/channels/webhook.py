"""Webhook channel implementation."""
import asyncio
from typing import Any, Callable, Optional

from aiohttp import web

from .base import Channel, ChannelType, InboundMessage, OutboundMessage


class WebhookChannel(Channel):
    """Webhook channel for HTTP API integration."""

    def __init__(self, config: dict):
        """Initialize webhook channel.

        Args:
            config: Configuration with 'host', 'port', 'path'
        """
        super().__init__(ChannelType.WEBHOOK, config)
        self.host = config.get("host", "0.0.0.0")
        self.port = config.get("port", 8080)
        self.path = config.get("path", "/webhook")
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None

    async def start(self) -> None:
        """Start webhook HTTP server."""
        self._app = web.Application()

        # Add routes
        self._app.router.add_post(self.path, self._handle_webhook)
        self._app.router.add_get("/health", self._handle_health)

        # Store channel reference for handler
        self._app["channel"] = self

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()

        print(f"Webhook channel started at http://{self.host}:{self.port}{self.path}")

    async def stop(self) -> None:
        """Stop webhook HTTP server."""
        if self._runner:
            await self._runner.cleanup()
        print("Webhook channel stopped")

    async def send_message(self, message: OutboundMessage) -> str:
        """Send message (not applicable for webhook, raises error)."""
        raise NotImplementedError("Webhook channel is inbound-only. Use HTTP client to send messages.")

    async def _handle_webhook(self, request: web.Request) -> web.Response:
        """Handle incoming webhook request."""
        try:
            data = await request.json()
        except:
            data = {}

        # Extract message info based on common formats
        content = ""
        user_id = ""
        chat_id = ""
        message_id = ""

        # Slack format
        if "event" in data:
            event = data.get("event", {})
            content = event.get("text", "")
            user_id = event.get("user", "")
            chat_id = event.get("channel", "")

        # Generic format
        elif "content" in data:
            content = data.get("content", "")
            user_id = data.get("user_id", "")
            chat_id = data.get("chat_id", "")
            message_id = data.get("message_id", "")

        # Feishu format
        elif "challenge" in data:
            # Verification request
            return web.json_response({"challenge": data.get("challenge")})

        if not content:
            return web.json_response({"status": "ok", "message": "No content"})

        inbound = InboundMessage(
            channel=self.channel_id,
            chat_id=chat_id,
            user_id=user_id,
            content=content,
            message_id=message_id,
            metadata=data,
        )

        await self.handle_inbound(inbound)

        return web.json_response({"status": "ok"})

    async def _handle_health(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({"status": "healthy"})
