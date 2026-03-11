"""Database integration tools."""
import json
import sqlite3
import asyncio
from typing import Any, Optional
from abc import ABC, abstractmethod
from pathlib import Path
from contextlib import asynccontextmanager

from src.tools.base import Tool, ToolResult, ToolCategory


class DatabaseAdapter(ABC):
    """Base class for database adapters."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection."""
        pass

    @abstractmethod
    async def execute(self, query: str, params: Optional[dict] = None) -> list[dict]:
        """Execute query and return results."""
        pass

    @abstractmethod
    async def execute_many(self, query: str, params_list: list[dict]) -> int:
        """Execute query with multiple parameter sets."""
        pass


class SQLiteAdapter(DatabaseAdapter):
    """SQLite database adapter."""

    def __init__(self, database: str = ":memory:"):
        """Initialize SQLite adapter.

        Args:
            database: Database path or ":memory:" for in-memory database.
        """
        self.database = database
        self._connection: Optional[sqlite3.Connection] = None

    async def connect(self) -> None:
        """Establish SQLite connection."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: sqlite3.connect(self.database, check_same_thread=False)
        )
        self._connection = sqlite3.connect(self.database, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row

    async def disconnect(self) -> None:
        """Close SQLite connection."""
        if self._connection:
            self._connection.close()
            self._connection = None

    async def execute(self, query: str, params: Optional[dict] = None) -> list[dict]:
        """Execute a query."""
        if not self._connection:
            await self.connect()

        cursor = self._connection.cursor()

        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)

        # If it's a SELECT query, return results
        if query.strip().upper().startswith("SELECT"):
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        else:
            # For INSERT/UPDATE/DELETE, commit and return affected rows
            self._connection.commit()
            return [{"affected_rows": cursor.rowcount}]

    async def execute_many(self, query: str, params_list: list[dict]) -> int:
        """Execute query with multiple parameter sets."""
        if not self._connection:
            await self.connect()

        cursor = self._connection.cursor()
        cursor.executemany(query, params_list)
        self._connection.commit()
        return cursor.rowcount


class PostgreSQLAdapter(DatabaseAdapter):
    """PostgreSQL database adapter."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "postgres",
        user: str = "postgres",
        password: str = "",
    ):
        """Initialize PostgreSQL adapter."""
        self.connection_string = (
            f"postgresql://{user}:{password}@{host}:{port}/{database}"
        )
        self._pool = None

    async def connect(self) -> None:
        """Establish PostgreSQL connection pool."""
        try:
            import asyncpg
        except ImportError:
            raise ImportError("asyncpg required. Install with: pip install asyncpg")

        self._pool = await asyncpg.create_pool(
            self.connection_string,
            min_size=1,
            max_size=10,
        )

    async def disconnect(self) -> None:
        """Close PostgreSQL connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def execute(self, query: str, params: Optional[dict] = None) -> list[dict]:
        """Execute a query."""
        if not self._pool:
            await self.connect()

        async with self._pool.acquire() as conn:
            if params:
                rows = await conn.fetch(query, *params.values())
            else:
                rows = await conn.fetch(query)

            return [dict(row) for row in rows]

    async def execute_many(self, query: str, params_list: list[dict]) -> int:
        """Execute query with multiple parameter sets."""
        if not self._pool:
            await self.connect()

        async with self._pool.acquire() as conn:
            await conn.executemany(query, params_list)
            return len(params_list)


class MySQLAdapter(DatabaseAdapter):
    """MySQL database adapter."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 3306,
        database: str = "mysql",
        user: str = "root",
        password: str = "",
    ):
        """Initialize MySQL adapter."""
        self.config = {
            "host": host,
            "port": port,
            "database": database,
            "user": user,
            "password": password,
        }
        self._pool = None

    async def connect(self) -> None:
        """Establish MySQL connection pool."""
        try:
            import aiomysql
        except ImportError:
            raise ImportError("aiomysql required. Install with: pip install aiomysql")

        self._pool = await aiomysql.create_pool(**self.config)

    async def disconnect(self) -> None:
        """Close MySQL connection pool."""
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None

    async def execute(self, query: str, params: Optional[dict] = None) -> list[dict]:
        """Execute a query."""
        if not self._pool:
            await self.connect()

        async with self._pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                if params:
                    await cursor.execute(query, params.values())
                else:
                    await cursor.execute(query)

                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def execute_many(self, query: str, params_list: list[dict]) -> int:
        """Execute query with multiple parameter sets."""
        if not self._pool:
            await self.connect()

        async with self._pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.executemany(query, [p.values() for p in params_list])
                return len(params_list)


class DatabaseTool(Tool):
    """Tool for database operations."""

    def __init__(self):
        super().__init__(
            name="database",
            description="Execute database queries (SQLite, PostgreSQL, MySQL)",
            category=ToolCategory.DATA_ACCESS,
        )
        self._adapters: dict[str, DatabaseAdapter] = {}

    async def execute(self, operation: str, **kwargs) -> ToolResult:
        """Execute database operation."""
        try:
            if operation == "connect":
                return await self._connect(
                    kwargs.get("name", "default"),
                    kwargs.get("type", "sqlite"),
                    kwargs.get("config", {}),
                )
            elif operation == "disconnect":
                return await self._disconnect(kwargs.get("name", "default"))
            elif operation == "query":
                return await self._query(
                    kwargs.get("name", "default"),
                    kwargs.get("query"),
                    kwargs.get("params"),
                )
            elif operation == "execute":
                return await self._execute(
                    kwargs.get("name", "default"),
                    kwargs.get("query"),
                    kwargs.get("params"),
                )
            elif operation == "list_tables":
                return await self._list_tables(kwargs.get("name", "default"))
            elif operation == "describe":
                return await self._describe(
                    kwargs.get("name", "default"),
                    kwargs.get("table"),
                )
            else:
                return ToolResult(success=False, error=f"Unknown operation: {operation}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _connect(
        self,
        name: str,
        db_type: str,
        config: dict,
    ) -> ToolResult:
        """Connect to a database."""
        if name in self._adapters:
            return ToolResult(success=False, error=f"Database already connected: {name}")

        try:
            if db_type == "sqlite":
                adapter = SQLiteAdapter(config.get("database", ":memory:"))
            elif db_type == "postgresql":
                adapter = PostgreSQLAdapter(
                    host=config.get("host", "localhost"),
                    port=config.get("port", 5432),
                    database=config.get("database", "postgres"),
                    user=config.get("user", "postgres"),
                    password=config.get("password", ""),
                )
            elif db_type == "mysql":
                adapter = MySQLAdapter(
                    host=config.get("host", "localhost"),
                    port=config.get("port", 3306),
                    database=config.get("database", "mysql"),
                    user=config.get("user", "root"),
                    password=config.get("password", ""),
                )
            else:
                return ToolResult(success=False, error=f"Unsupported database type: {db_type}")

            await adapter.connect()
            self._adapters[name] = adapter

            return ToolResult(success=True, data={"name": name, "type": db_type})
        except ImportError as e:
            return ToolResult(success=False, error=str(e))

    async def _disconnect(self, name: str) -> ToolResult:
        """Disconnect from a database."""
        if name not in self._adapters:
            return ToolResult(success=False, error=f"Database not connected: {name}")

        await self._adapters[name].disconnect()
        del self._adapters[name]

        return ToolResult(success=True, data={"name": name})

    async def _query(
        self,
        name: str,
        query: str,
        params: Optional[dict],
    ) -> ToolResult:
        """Execute a SELECT query."""
        if name not in self._adapters:
            return ToolResult(success=False, error=f"Database not connected: {name}")

        results = await self._adapters[name].execute(query, params)

        return ToolResult(
            success=True,
            data={
                "rows": results,
                "count": len(results),
            },
        )

    async def _execute(
        self,
        name: str,
        query: str,
        params: Optional[dict],
    ) -> ToolResult:
        """Execute an INSERT/UPDATE/DELETE query."""
        if name not in self._adapters:
            return ToolResult(success=False, error=f"Database not connected: {name}")

        results = await self._adapters[name].execute(query, params)

        return ToolResult(success=True, data={"result": results})

    async def _list_tables(self, name: str) -> ToolResult:
        """List all tables in the database."""
        if name not in self._adapters:
            return ToolResult(success=False, error=f"Database not connected: {name}")

        adapter = self._adapters[name]

        # Different SQL for different databases
        if isinstance(adapter, SQLiteAdapter):
            query = "SELECT name FROM sqlite_master WHERE type='table'"
        elif isinstance(adapter, PostgreSQLAdapter):
            query = "SELECT tablename FROM pg_tables WHERE schemaname='public'"
        elif isinstance(adapter, MySQLAdapter):
            query = "SHOW TABLES"
        else:
            return ToolResult(success=False, error="Unsupported database type")

        results = await adapter.execute(query)

        tables = [list(row.values())[0] for row in results]

        return ToolResult(success=True, data={"tables": tables, "count": len(tables)})

    async def _describe(self, name: str, table: str) -> ToolResult:
        """Describe table structure."""
        if name not in self._adapters:
            return ToolResult(success=False, error=f"Database not connected: {name}")

        adapter = self._adapters[name]

        if isinstance(adapter, SQLiteAdapter):
            query = f"PRAGMA table_info({table})"
        elif isinstance(adapter, PostgreSQLAdapter):
            query = f"""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = '{table}'
            """
        elif isinstance(adapter, MySQLAdapter):
            query = f"DESCRIBE {table}"
        else:
            return ToolResult(success=False, error="Unsupported database type")

        results = await adapter.execute(query)

        return ToolResult(success=True, data={"columns": results})


class HTTPClientTool(Tool):
    """Tool for making HTTP requests to external APIs."""

    def __init__(self):
        super().__init__(
            name="http_client",
            description="Make HTTP requests to external APIs",
            category=ToolCategory.DATA_ACCESS,
        )
        self._session = None

    async def execute(self, operation: str, **kwargs) -> ToolResult:
        """Execute HTTP operation."""
        try:
            import aiohttp
        except ImportError:
            return ToolResult(success=False, error="aiohttp required. Install with: pip install aiohttp")

        async with aiohttp.ClientSession() as session:
            if operation == "get":
                return await self._request(
                    session,
                    "GET",
                    kwargs.get("url"),
                    params=kwargs.get("params"),
                    headers=kwargs.get("headers"),
                )
            elif operation == "post":
                return await self._request(
                    session,
                    "POST",
                    kwargs.get("url"),
                    data=kwargs.get("data"),
                    json=kwargs.get("json"),
                    headers=kwargs.get("headers"),
                )
            elif operation == "put":
                return await self._request(
                    session,
                    "PUT",
                    kwargs.get("url"),
                    data=kwargs.get("data"),
                    json=kwargs.get("json"),
                    headers=kwargs.get("headers"),
                )
            elif operation == "delete":
                return await self._request(
                    session,
                    "DELETE",
                    kwargs.get("url"),
                    headers=kwargs.get("headers"),
                )
            else:
                return ToolResult(success=False, error=f"Unknown operation: {operation}")

    async def _request(
        self,
        session: Any,
        method: str,
        url: str,
        **kwargs,
    ) -> ToolResult:
        """Make an HTTP request."""
        if not url:
            return ToolResult(success=False, error="URL is required")

        headers = kwargs.get("headers", {})
        timeout = aiohttp.ClientTimeout(total=30)

        async with session.request(
            method,
            url,
            params=kwargs.get("params"),
            data=kwargs.get("data"),
            json=kwargs.get("json"),
            headers=headers,
            timeout=timeout,
        ) as response:
            # Try to parse JSON, fall back to text
            try:
                data = await response.json()
            except:
                data = await response.text()

            return ToolResult(
                success=True,
                data={
                    "status": response.status,
                    "headers": dict(response.headers),
                    "data": data,
                },
            )
