"""Utility functions and helpers."""
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, urljoin


def generate_id(prefix: str = "") -> str:
    """Generate a unique ID."""
    uid = uuid.uuid4().hex[:8]
    return f"{prefix}{uid}" if prefix else uid


def hash_string(s: str, algorithm: str = "md5") -> str:
    """Hash a string."""
    if algorithm == "md5":
        return hashlib.md5(s.encode()).hexdigest()
    elif algorithm == "sha256":
        return hashlib.sha256(s.encode()).hexdigest()
    else:
        raise ValueError(f"Unknown algorithm: {algorithm}")


def timestamp_now() -> float:
    """Get current timestamp."""
    return datetime.now(timezone.utc).timestamp()


def format_timestamp(ts: float, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format timestamp."""
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime(fmt)


def parse_json_safe(s: str, default: Any = None) -> Any:
    """Safely parse JSON."""
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return default


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename."""
    # Remove invalid characters
    filename = re.sub(r'[<>:"/\\|?*]', "", filename)
    # Limit length
    return filename[:255]


def truncate_string(s: str, max_length: int = 100, suffix: str = "...") -> str:
    """Truncate a string."""
    if len(s) <= max_length:
        return s
    return s[:max_length - len(suffix)] + suffix


def extract_urls(text: str) -> List[str]:
    """Extract URLs from text."""
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    return re.findall(url_pattern, text)


def validate_url(url: str) -> bool:
    """Validate a URL."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False


def merge_dicts(*dicts: Dict) -> Dict:
    """Merge multiple dictionaries."""
    result = {}
    for d in dicts:
        if d:
            result.update(d)
    return result


def flatten_dict(d: Dict, parent_key: str = "", sep: str = ".") -> Dict:
    """Flatten a nested dictionary."""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def chunk_list(lst: List, chunk_size: int) -> List[List]:
    """Split a list into chunks."""
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


def retry(max_attempts: int = 3, delay: float = 1.0):
    """Decorator for retrying functions."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            import asyncio

            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(delay)

            raise last_exception

        return wrapper
    return decorator


class RateLimiter:
    """Simple rate limiter."""

    def __init__(self, max_calls: int, period: float):
        """Initialize rate limiter.

        Args:
            max_calls: Maximum calls allowed in period
            period: Time period in seconds
        """
        self.max_calls = max_calls
        self.period = period
        self._calls: List[float] = []

    async def acquire(self) -> None:
        """Wait until rate limit allows."""
        import asyncio

        now = timestamp_now()

        # Remove old calls
        self._calls = [ts for ts in self._calls if now - ts < self.period]

        if len(self._calls) >= self.max_calls:
            # Wait until oldest call expires
            wait_time = self.period - (now - self._calls[0])
            if wait_time > 0:
                await asyncio.sleep(wait_time)

        self._calls.append(timestamp_now())


class Cache:
    """Simple in-memory cache with TTL."""

    def __init__(self, default_ttl: float = 300):
        """Initialize cache.

        Args:
            default_ttl: Default TTL in seconds
        """
        self.default_ttl = default_ttl
        self._cache: Dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if key in self._cache:
            value, expiry = self._cache[key]
            if timestamp_now() < expiry:
                return value
            del self._cache[key]
        return None

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """Set value in cache."""
        ttl = ttl or self.default_ttl
        expiry = timestamp_now() + ttl
        self._cache[key] = (value, expiry)

    def delete(self, key: str) -> bool:
        """Delete value from cache."""
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def clear(self) -> None:
        """Clear all cache."""
        self._cache.clear()
