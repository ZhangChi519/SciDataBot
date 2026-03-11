"""Persistent storage module."""
import json
import os
import time
import sqlite3
import hashlib
from pathlib import Path
from typing import Any, Optional
from abc import ABC, abstractmethod

import aiofiles


class StorageBackend(ABC):
    """Base class for storage backends."""

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Get value by key."""
        pass

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value with optional TTL (seconds)."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete key."""
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        pass

    @abstractmethod
    async def keys(self, pattern: str = "*") -> list[str]:
        """List keys matching pattern."""
        pass

    @abstractmethod
    async def clear(self) -> None:
        """Clear all data."""
        pass


class MemoryStorage(StorageBackend):
    """In-memory storage backend (for testing/caching)."""

    def __init__(self):
        self._data: dict[str, tuple[Any, Optional[float]]] = {}

    async def get(self, key: str) -> Optional[Any]:
        if key not in self._data:
            return None

        value, expiry = self._data[key]
        if expiry and time.time() > expiry:
            del self._data[key]
            return None

        return value

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        expiry = time.time() + ttl if ttl else None
        self._data[key] = (value, expiry)
        return True

    async def delete(self, key: str) -> bool:
        if key in self._data:
            del self._data[key]
            return True
        return False

    async def exists(self, key: str) -> bool:
        value = await self.get(key)
        return value is not None

    async def keys(self, pattern: str = "*") -> list[str]:
        import fnmatch
        return [k for k in self._data.keys() if fnmatch.fnmatch(k, pattern)]

    async def clear(self) -> None:
        self._data.clear()


class FileStorage(StorageBackend):
    """File-based storage backend."""

    def __init__(self, base_dir: str = "./data/storage"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(self, key: str) -> Path:
        """Get file path for key."""
        key_hash = hashlib.md5(key.encode()).hexdigest()
        return self.base_dir / f"{key_hash}.json"

    async def get(self, key: str) -> Optional[Any]:
        path = self._get_path(key)
        if not path.exists():
            return None

        try:
            async with aiofiles.open(path, "r") as f:
                content = await f.read()
                data = json.loads(content)

                # Check expiry
                if data.get("expiry") and time.time() > data["expiry"]:
                    await self.delete(key)
                    return None

                return data["value"]
        except Exception:
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        path = self._get_path(key)

        data = {"value": value}
        if ttl:
            data["expiry"] = time.time() + ttl

        try:
            async with aiofiles.open(path, "w") as f:
                await f.write(json.dumps(data))
            return True
        except Exception:
            return False

    async def delete(self, key: str) -> bool:
        path = self._get_path(key)
        if path.exists():
            path.unlink()
            return True
        return False

    async def exists(self, key: str) -> bool:
        return self._get_path(key).exists()

    async def keys(self, pattern: str = "*") -> list[str]:
        import fnmatch

        keys = []
        for path in self.base_dir.glob("*.json"):
            try:
                async with aiofiles.open(path, "r") as f:
                    content = await f.read()
                    data = json.loads(content)

                    # Check expiry
                    if data.get("expiry") and time.time() > data["expiry"]:
                        path.unlink()
                        continue

                    # Reconstruct key from filename
                    key = path.stem  # This is the hash, not the original key
                    if fnmatch.fnmatch(key, pattern):
                        keys.append(key)
            except Exception:
                continue

        return keys

    async def clear(self) -> None:
        for path in self.base_dir.glob("*.json"):
            path.unlink()


class SQLiteStorage(StorageBackend):
    """SQLite-based storage backend with key-value interface."""

    def __init__(self, database: str = "./data/storage.db"):
        self.database = database
        Path(database).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        conn = sqlite3.connect(self.database)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS storage (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                expiry REAL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_expiry ON storage(expiry)
        """)

        conn.commit()
        conn.close()

    async def get(self, key: str) -> Optional[Any]:
        conn = sqlite3.connect(self.database)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT value, expiry FROM storage WHERE key = ?",
            (key,)
        )

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        value_json, expiry = row

        # Check expiry
        if expiry and time.time() > expiry:
            await self.delete(key)
            return None

        return json.loads(value_json)

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        value_json = json.dumps(value)
        expiry = time.time() + ttl if ttl else None
        now = time.time()

        conn = sqlite3.connect(self.database)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO storage (key, value, expiry, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                expiry = excluded.expiry,
                updated_at = excluded.updated_at
            """,
            (key, value_json, expiry, now, now)
        )

        conn.commit()
        conn.close()
        return True

    async def delete(self, key: str) -> bool:
        conn = sqlite3.connect(self.database)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM storage WHERE key = ?", (key,))

        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()

        return deleted

    async def exists(self, key: str) -> bool:
        conn = sqlite3.connect(self.database)
        cursor = conn.cursor()

        cursor.execute("SELECT expiry FROM storage WHERE key = ?", (key,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return False

        expiry = row[0]
        if expiry and time.time() > expiry:
            await self.delete(key)
            return False

        return True

    async def keys(self, pattern: str = "*") -> list[str]:
        import fnmatch

        conn = sqlite3.connect(self.database)
        cursor = conn.cursor()

        # Clean up expired keys
        cursor.execute("DELETE FROM storage WHERE expiry IS NOT NULL AND expiry < ?", (time.time(),))
        conn.commit()

        cursor.execute("SELECT key FROM storage")
        rows = cursor.fetchall()
        conn.close()

        keys = [row[0] for row in rows]
        return [k for k in keys if fnmatch.fnmatch(k, pattern)]

    async def clear(self) -> None:
        conn = sqlite3.connect(self.database)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM storage")

        conn.commit()
        conn.close()


class SessionStore:
    """Session storage with automatic expiration."""

    def __init__(self, storage: StorageBackend, default_ttl: int = 3600):
        self.storage = storage
        self.default_ttl = default_ttl

    async def create_session(
        self,
        session_id: str,
        data: dict,
        ttl: Optional[int] = None,
    ) -> bool:
        """Create a new session."""
        key = f"session:{session_id}"
        return await self.storage.set(key, data, ttl or self.default_ttl)

    async def get_session(self, session_id: str) -> Optional[dict]:
        """Get session data."""
        key = f"session:{session_id}"
        return await self.storage.get(key)

    async def update_session(
        self,
        session_id: str,
        data: dict,
        extend_ttl: bool = True,
    ) -> bool:
        """Update session data."""
        key = f"session:{session_id}"
        existing = await self.storage.get(key)

        if existing is None:
            return await self.create_session(session_id, data)

        # Merge data
        existing.update(data)

        ttl = self.default_ttl if extend_ttl else None
        return await self.storage.set(key, existing, ttl)

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        key = f"session:{session_id}"
        return await self.storage.delete(key)

    async def list_sessions(self) -> list[str]:
        """List all active session IDs."""
        return await self.storage.keys("session:*")


class Cache:
    """Cache wrapper with common operations."""

    def __init__(self, storage: StorageBackend):
        self.storage = storage

    async def get_or_set(
        self,
        key: str,
        factory: Any,
        ttl: Optional[int] = None,
        *args,
        **kwargs,
    ) -> Any:
        """Get from cache or compute and store."""
        value = await self.storage.get(key)

        if value is not None:
            return value

        # Compute value
        if asyncio.iscoroutinefunction(factory):
            value = await factory(*args, **kwargs)
        else:
            value = factory(*args, **kwargs)

        # Store in cache
        await self.storage.set(key, value, ttl)

        return value

    async def invalidate(self, key: str) -> bool:
        """Invalidate a cache entry."""
        return await self.storage.delete(key)

    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate all keys matching pattern."""
        keys = await self.storage.keys(pattern)
        count = 0
        for key in keys:
            if await self.storage.delete(key):
                count += 1
        return count


# Import asyncio for iscoroutinefunction check
import asyncio
