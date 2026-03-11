"""Session management for maintaining conversation context."""
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from threading import Lock


@dataclass
class Session:
    """Represents a conversation session with message history."""

    session_id: str
    channel: str
    chat_id: str
    user_id: str
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    context: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    messages: List[Dict[str, Any]] = field(default_factory=list)
    last_consolidated: int = 0

    def add_message(self, role: str, content: str, **kwargs) -> None:
        """Add a message to session history."""
        message = {
            "role": role,
            "content": content,
            "timestamp": time.time(),
            **kwargs
        }
        self.messages.append(message)
        self.update()

    def get_history(self, max_messages: int = 50) -> List[Dict[str, Any]]:
        """Get recent message history."""
        return self.messages[-max_messages:] if self.messages else []

    def get_unconsolidated_count(self) -> int:
        """Get number of messages since last consolidation."""
        return len(self.messages) - self.last_consolidated

    def clear(self) -> None:
        """Clear session messages."""
        self.messages = []
        self.last_consolidated = 0

    def update(self) -> None:
        """Update the session's updated_at timestamp."""
        self.updated_at = time.time()

    def is_expired(self, ttl: int) -> bool:
        """Check if session has expired."""
        return time.time() - self.updated_at > ttl


class SessionManager:
    """Manages multiple conversation sessions."""

    def __init__(self, default_ttl: int = 3600):
        """Initialize session manager.

        Args:
            default_ttl: Default time-to-live in seconds (1 hour).
        """
        self.default_ttl = default_ttl
        self._sessions: Dict[str, Session] = {}
        self._lock = Lock()

    def create_session(
        self,
        channel: str,
        chat_id: str,
        user_id: str,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Session:
        """Create a new session.

        Args:
            channel: Channel identifier
            chat_id: Chat/room identifier
            user_id: User identifier
            session_id: Optional session ID (generated if not provided)
            metadata: Optional initial metadata

        Returns:
            Created session
        """
        with self._lock:
            # Check if session already exists for this channel:chat_id
            existing = self._find_session(channel, chat_id, user_id)
            if existing:
                existing.update()
                return existing

            session = Session(
                session_id=session_id or str(uuid.uuid4()),
                channel=channel,
                chat_id=chat_id,
                user_id=user_id,
                metadata=metadata or {},
            )

            self._sessions[session.session_id] = session
            return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get session by ID."""
        with self._lock:
            return self._sessions.get(session_id)

    def get_or_create_session(
        self,
        channel: str,
        chat_id: str,
        user_id: str,
    ) -> Session:
        """Get existing session or create new one."""
        with self._lock:
            existing = self._find_session(channel, chat_id, user_id)
            if existing:
                existing.update()
                return existing

            return self.create_session(channel, chat_id, user_id)

    def _find_session(
        self,
        channel: str,
        chat_id: str,
        user_id: str,
    ) -> Optional[Session]:
        """Find session by channel, chat_id, and user_id."""
        for session in self._sessions.values():
            if session.channel == channel and session.chat_id == chat_id:
                return session
        return None

    def update_session(
        self,
        session_id: str,
        context: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Update session context or metadata."""
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False

            if context:
                session.context.update(context)

            if metadata:
                session.metadata.update(metadata)

            session.update()
            return True

    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False

    def list_sessions(
        self,
        channel: Optional[str] = None,
        include_expired: bool = False,
    ) -> list[Session]:
        """List all sessions, optionally filtered by channel."""
        with self._lock:
            sessions = list(self._sessions.values())

            if channel:
                sessions = [s for s in sessions if s.channel == channel]

            if not include_expired:
                sessions = [s for s in sessions if not s.is_expired(self.default_ttl)]

            return sessions

    def cleanup_expired(self) -> int:
        """Remove expired sessions.

        Returns:
            Number of sessions removed
        """
        with self._lock:
            expired = [
                sid for sid, s in self._sessions.items()
                if s.is_expired(self.default_ttl)
            ]

            for sid in expired:
                del self._sessions[sid]

            return len(expired)

    def get_session_count(self) -> int:
        """Get total number of sessions."""
        with self._lock:
            return len(self._sessions)

    def get_or_create_context(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        """Get or create context for a session."""
        session = self.get_session(session_id)
        if session:
            return session.context

        # Return empty context if session doesn't exist
        return {}


# Global session manager instance
_global_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """Get the global session manager instance."""
    global _global_manager
    if _global_manager is None:
        _global_manager = SessionManager()
    return _global_manager


def set_session_manager(manager: SessionManager) -> None:
    """Set the global session manager instance."""
    global _global_manager
    _global_manager = manager
