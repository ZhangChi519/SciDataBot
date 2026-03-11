"""Telegram channel implementation."""
import asyncio
from typing import Any, Optional

from .base import Channel, ChannelType, InboundMessage, OutboundMessage


class TelegramChannel(Channel):
    """Telegram bot channel."""

    def __init__(self, config: dict):
        """Initialize Telegram channel.

        Args:
            config: Configuration with 'token' and optional 'api_url'
        """
        super().__init__(ChannelType.TELEGRAM, config)
        self.token = config.get("token")
        self.api_url = config.get("api_url", "https://api.telegram.org")
        self._running = False
        self._offset = 0
        self._polling_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start Telegram bot and begin polling."""
        if not self.token:
            raise ValueError("Telegram bot token is required")

        # Test connection
        await self._api_request("getMe")

        self._running = True
        self._polling_task = asyncio.create_task(self._poll_updates())
        print(f"Telegram channel started (token: ...{self.token[-4:]})")

    async def stop(self) -> None:
        """Stop Telegram bot polling."""
        self._running = False
        if self._polling_task:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass
        print("Telegram channel stopped")

    async def send_message(self, message: OutboundMessage) -> str:
        """Send message to Telegram."""
        payload = {
            "chat_id": message.chat_id,
            "text": message.content,
        }

        if message.reply_to:
            payload["reply_to_message_id"] = message.reply_to

        result = await self._api_request("sendMessage", payload)
        return str(result.get("result", {}).get("message_id"))

    async def _poll_updates(self) -> None:
        """Poll Telegram for updates."""
        while self._running:
            try:
                updates = await self._api_request(
                    "getUpdates",
                    {"offset": self._offset, "timeout": 30}
                )

                for update in updates.get("result", []):
                    self._offset = update.get("update_id", 0) + 1

                    message = update.get("message")
                    if not message:
                        continue

                    # Only handle text messages
                    if "text" not in message:
                        continue

                    chat = message.get("chat", {})
                    user = message.get("from", {})

                    inbound = InboundMessage(
                        channel=self.channel_id,
                        chat_id=str(chat.get("id", "")),
                        user_id=str(user.get("id", "")),
                        content=message.get("text", ""),
                        message_id=str(message.get("message_id", "")),
                        metadata={
                            "chat": chat,
                            "user": user,
                        },
                    )

                    await self.handle_inbound(inbound)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error polling Telegram: {e}")
                await asyncio.sleep(5)

    async def _api_request(self, method: str, params: dict = None) -> dict:
        """Make API request to Telegram."""
        import aiohttp

        url = f"{self.api_url}/bot{self.token}/{method}"

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=params or {}) as response:
                result = await response.json()

                if not result.get("ok"):
                    raise Exception(f"Telegram API error: {result.get('description')}")

                return result
