"""Console channel implementation."""
import asyncio
from typing import Any

from .base import Channel, ChannelType, InboundMessage, OutboundMessage


class ConsoleChannel(Channel):
    """Console/Terminal channel for interactive testing."""

    def __init__(self, config: dict = None):
        super().__init__(ChannelType.CONSOLE, config or {})
        self._running = False

    async def start(self) -> None:
        """Start console input listener."""
        self._running = True
        print("Console channel started. Type your messages (Ctrl+C to exit).")

        while self._running:
            try:
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None, input, "\nYou: "
                )

                if not user_input.strip():
                    continue

                message = InboundMessage(
                    channel=self.channel_id,
                    chat_id="console",
                    user_id="user",
                    content=user_input.strip(),
                )

                # Handle message and print response
                response = await self.handle_inbound(message)
                if response:
                    print(f"\nBot: {response}")

            except KeyboardInterrupt:
                print("\nExiting...")
                break
            except EOFError:
                break
            except UnicodeDecodeError:
                print("\nInput encoding error, please try again.")
                continue
            except Exception as e:
                print(f"\nError: {e}")
                continue

        await self.stop()

    async def stop(self) -> None:
        """Stop console channel."""
        self._running = False

    async def send_message(self, message: OutboundMessage) -> str:
        """Send message to console."""
        print(f"\nBot: {message.content}")
        return f"console_{id(message)}"
