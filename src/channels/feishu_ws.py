"""Feishu WebSocket channel — uses lark_oapi SDK in a background thread."""
import asyncio
import fcntl
import json
import os
import threading
from pathlib import Path
from typing import Any, Optional

from .base import Channel, ChannelType, InboundMessage, OutboundMessage


class FeishuWSChannel(Channel):
    """Feishu long-connection channel via lark_oapi SDK.

    The SDK blocks on its own event loop, so we run it in a daemon thread.
    Received events are forwarded to the main asyncio loop via
    run_coroutine_threadsafe.
    """

    def __init__(self, config: dict):
        super().__init__(ChannelType.FEISHU_WS, config)
        self.app_id = config.get("app_id", "")
        self.app_secret = config.get("app_secret", "")
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None
        self._sdk_thread: Optional[threading.Thread] = None
        self._ws_client: Optional[Any] = None
        self._session_aio: Optional[Any] = None  # aiohttp for send_message
        self._lock_file = Path.home() / ".scidatabot" / "feishu_ws.lock"
        self._lock_fd: Optional[int] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if not self.app_id or not self.app_secret:
            raise ValueError("Feishu app_id and app_secret are required")

        self._lock_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._lock_fd = os.open(str(self._lock_file), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, FileExistsError):
            if self._lock_fd is not None:
                os.close(self._lock_fd)
                self._lock_fd = None
            raise RuntimeError(
                "Feishu WebSocket is already running! "
                "Only one instance can connect to Feishu at a time. "
                "Please stop the existing instance first."
            )

        import aiohttp
        self._session_aio = aiohttp.ClientSession()
        self._main_loop = asyncio.get_event_loop()

        self._sdk_thread = threading.Thread(
            target=self._run_sdk, daemon=True, name="feishu-ws-sdk"
        )
        self._sdk_thread.start()
        print(f"Feishu WebSocket channel starting (app_id: ...{self.app_id[-4:]})")

    def _run_sdk(self) -> None:
        """Run lark_oapi WS SDK in its own thread with its own event loop."""
        import lark_oapi as lark
        from lark_oapi.ws import client as ws_module

        # Give SDK its own loop so it doesn't conflict with the main asyncio loop.
        sdk_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(sdk_loop)
        ws_module.loop = sdk_loop

        def on_message(data) -> None:
            """Called by SDK for every im.message.receive_v1 event (sync)."""
            try:
                # data is a P2ImMessageReceiveV1 object
                msg = data.event.message
                sender = data.event.sender
                message_id = msg.message_id or ""
                chat_id = msg.chat_id or ""
                msg_type = msg.message_type or "text"
                content_raw = msg.content or "{}"
                sender_id = (sender.sender_id.open_id or "") if sender and sender.sender_id else ""

                content = self._parse_content(msg_type, content_raw)
                print(f"[FeishuWS] message received: {content[:50]}", flush=True)
                inbound = InboundMessage(
                    channel=self.channel_id,
                    chat_id=chat_id,
                    sender_id=sender_id,
                    content=content,
                    metadata={"msg_type": msg_type, "message_id": message_id},
                )
                asyncio.run_coroutine_threadsafe(
                    self.handle_inbound(inbound), self._main_loop
                )
            except Exception as e:
                print(f"[FeishuWS] on_message error: {e}", flush=True)

        def on_message_read(data) -> None:
            """Called for im.message.message_read_v1 event."""
            print(f"[FeishuWS] message read event received", flush=True)

        handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(on_message)
            .register_p2_im_message_message_read_v1(on_message_read)
            .build()
        )

        self._ws_client = lark.ws.Client(
            self.app_id,
            self.app_secret,
            event_handler=handler,
            log_level=lark.LogLevel.DEBUG,
        )
        try:
            self._ws_client.start()  # blocks forever
        except Exception as e:
            print(f"[FeishuWS] SDK error: {e}", flush=True)

    async def stop(self) -> None:
        if self._session_aio:
            await self._session_aio.close()
            self._session_aio = None
        if self._lock_fd is not None:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            os.close(self._lock_fd)
            self._lock_fd = None
        try:
            self._lock_file.unlink(missing_ok=True)
        except Exception:
            pass
        print("Feishu WebSocket channel stopped")

    # ------------------------------------------------------------------
    # Outbound
    # ------------------------------------------------------------------

    async def send_message(self, message: OutboundMessage) -> str:
        if not self._session_aio:
            raise RuntimeError("session not initialized")
        try:
            token_url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
            async with self._session_aio.post(
                token_url,
                json={"app_id": self.app_id, "app_secret": self.app_secret},
                ssl=False,
            ) as resp:
                tok = await resp.json()

            if tok.get("code") != 0:
                raise RuntimeError(f"token error: {tok}")

            headers = {
                "Authorization": f"Bearer {tok['tenant_access_token']}",
                "Content-Type": "application/json; charset=utf-8",
            }
            content_json = json.dumps({"text": message.content})

            if message.reply_to:
                url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message.reply_to}/reply"
                payload = {"msg_type": "text", "content": content_json}
            else:
                url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
                payload = {
                    "receive_id": message.chat_id,
                    "msg_type": "text",
                    "content": content_json,
                }

            async with self._session_aio.post(
                url, json=payload, headers=headers, ssl=False
            ) as resp:
                result = await resp.json()
                if result.get("code") != 0:
                    print(f"[FeishuWS] send error: {result}")
                    return ""
                return result.get("data", {}).get("message_id", "")
        except Exception as e:
            print(f"[FeishuWS] send_message error: {e}")
            return ""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_content(self, msg_type: str, content: str) -> str:
        if msg_type == "text":
            try:
                return json.loads(content).get("text", content)
            except (json.JSONDecodeError, AttributeError):
                return content
        return content
