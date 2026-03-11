"""Feishu (Lark) channel implementation."""
import asyncio
import hashlib
import time
import base64
import hmac
from typing import Any, Optional
from urllib.parse import parse_qs

from .base import Channel, ChannelType, InboundMessage, OutboundMessage


class FeishuChannel(Channel):
    """Feishu (Lark) bot channel."""

    def __init__(self, config: dict):
        """Initialize Feishu channel.

        Args:
            config: Configuration with 'app_id', 'app_secret', 'verification_token'
        """
        super().__init__(ChannelType.FEISHU, config)
        self.app_id = config.get("app_id")
        self.app_secret = config.get("app_secret")
        self.verification_token = config.get("verification_token")
        self._access_token: Optional[str] = None
        self._token_expires_at = 0

    async def start(self) -> None:
        """Start Feishu bot."""
        if not self.app_id or not self.app_secret:
            raise ValueError("Feishu app_id and app_secret are required")

        await self._get_access_token()
        print(f"Feishu channel started (app_id: ...{self.app_id[-4:]})")

    async def stop(self) -> None:
        """Stop Feishu channel."""
        self._access_token = None
        print("Feishu channel stopped")

    async def send_message(self, message: OutboundMessage) -> str:
        """Send message to Feishu."""
        # Send using Feishu IM API
        payload = {
            "receive_id": message.chat_id,
            "msg_type": "text",
            "content": {"text": message.content},
        }

        result = await self._api_request("im/v1/messages", method="POST", payload=payload)
        return result.get("data", {}).get("message_id", "")

    async def verify_request(self, timestamp: str, signature: str) -> bool:
        """Verify Feishu webhook request signature."""
        if not self.app_secret:
            return False

        # Build string to sign
        string_to_sign = f"{timestamp}{self.app_secret}"
        string_to_sign_bytes = string_to_sign.encode("utf-8")

        # HMAC-SHA256
        hmac_code = hmac.new(
            string_to_sign_bytes,
            digestmod=hashlib.sha256
        ).digest()

        # Base64 encode
        signature_encoded = base64.b64encode(hmac_code).decode("utf-8")

        return signature_encoded == signature

    async def _get_access_token(self) -> str:
        """Get or refresh Feishu access token."""
        if self._access_token and time.time() < self._token_expires_at - 300:
            return self._access_token

        payload = {
            "app_id": self.app_id,
            "app_secret": self.app_secret,
        }

        result = await self._api_request("open-apis/auth/v3/tenant_access_token/internal", method="POST", payload=payload)

        self._access_token = result.get("tenant_access_token")
        expire = result.get("expire", 7200)
        self._token_expires_at = time.time() + expire

        return self._access_token

    async def _api_request(
        self,
        path: str,
        method: str = "GET",
        payload: dict = None,
    ) -> dict:
        """Make API request to Feishu."""
        import aiohttp

        # Get access token
        await self._get_access_token()

        url = f"https://open.feishu.cn/{path}"
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json; charset=utf-8",
        }

        async with aiohttp.ClientSession() as session:
            if method == "GET":
                async with session.get(url, headers=headers) as response:
                    result = await response.json()
            else:
                async with session.post(url, json=payload, headers=headers) as response:
                    result = await response.json()

        if result.get("code") and result.get("code") != 0:
            raise Exception(f"Feishu API error: {result.get('msg')}")

        return result


class FeishuWebHookChannel(Channel):
    """Feishu Webhook channel (simpler, outgoing only)."""

    def __init__(self, config: dict):
        """Initialize Feishu webhook channel.

        Args:
            config: Configuration with 'webhook_url'
        """
        super().__init__(ChannelType.FEISHU, config)
        self.webhook_url = config.get("webhook_url")

    async def start(self) -> None:
        """Start webhook channel."""
        if not self.webhook_url:
            raise ValueError("Feishu webhook_url is required")
        print(f"Feishu webhook channel ready")

    async def stop(self) -> None:
        """Stop webhook channel."""
        pass

    async def send_message(self, message: OutboundMessage) -> str:
        """Send message via Feishu webhook."""
        import aiohttp

        payload = {
            "msg_type": "text",
            "content": {"text": message.content},
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(self.webhook_url, json=payload) as response:
                if response.status != 200:
                    raise Exception(f"Feishu webhook error: {response.status}")

        return "webhook_sent"
