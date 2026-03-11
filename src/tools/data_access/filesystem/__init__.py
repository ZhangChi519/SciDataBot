"""File system operations tool."""
import os
import glob as glob_module
import shutil
import tempfile
import hashlib
from pathlib import Path
from typing import Any, Optional

from src.tools.base import Tool, ToolResult, ToolCategory


class FileSystemTool(Tool):
    """Tool for file system operations."""

    name = "filesystem"
    description = "File system operations: read, write, list, copy, move, delete files"
    category = ToolCategory.DATA_ACCESS

    def __init__(
        self,
        allowed_directories: Optional[list[str]] = None,
        max_file_size: int = 100 * 1024 * 1024,  # 100MB
    ):
        """Initialize file system tool.

        Args:
            allowed_directories: List of directories to allow access. If None, allows all.
            max_file_size: Maximum file size to read in bytes.
        """
        self.allowed_directories = allowed_directories
        self.max_file_size = max_file_size

    def _validate_path(self, path: str) -> Path:
        """Validate and resolve a file path."""
        resolved = Path(path).resolve()

        if self.allowed_directories:
            allowed = [Path(d).resolve() for d in self.allowed_directories]
            if not any(str(resolved).startswith(str(a)) for a in allowed):
                raise PermissionError(f"Access denied: {path} not in allowed directories")

        return resolved

    async def execute(self, operation: str, **kwargs) -> ToolResult:
        """Execute file system operation.

        Args:
            operation: Operation to perform (read, write, list, copy, move, delete, exists, stats, glob, search)
            **kwargs: Operation-specific arguments.

        Returns:
            ToolResult with operation output.
        """
        try:
            if operation == "read":
                return await self._read_file(kwargs.get("path"))
            elif operation == "write":
                return await self._write_file(kwargs.get("path"), kwargs.get("content", ""))
            elif operation == "list":
                return await self._list_directory(kwargs.get("path", "."))
            elif operation == "copy":
                return await self._copy(kwargs.get("source"), kwargs.get("destination"))
            elif operation == "move":
                return await self._move(kwargs.get("source"), kwargs.get("destination"))
            elif operation == "delete":
                return await self._delete(kwargs.get("path"))
            elif operation == "exists":
                return await self._exists(kwargs.get("path"))
            elif operation == "stats":
                return await self._stats(kwargs.get("path"))
            elif operation == "glob":
                return await self._glob(kwargs.get("pattern"), kwargs.get("path"))
            elif operation == "search":
                return await self._search(kwargs.get("path"), kwargs.get("pattern"))
            else:
                return ToolResult(success=False, error=f"Unknown operation: {operation}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _read_file(self, path: str) -> ToolResult:
        """Read file contents."""
        if not path:
            return ToolResult(success=False, error="Path is required")

        resolved = self._validate_path(path)

        if not resolved.exists():
            return ToolResult(success=False, error=f"File not found: {path}")

        if not resolved.is_file():
            return ToolResult(success=False, error=f"Not a file: {path}")

        size = resolved.stat().st_size
        if size > self.max_file_size:
            return ToolResult(success=False, error=f"File too large: {size} bytes (max: {self.max_file_size})")

        content = resolved.read_text(encoding="utf-8")
        return ToolResult(
            success=True,
            data={
                "path": str(resolved),
                "size": size,
                "content": content,
            },
        )

    async def _write_file(self, path: str, content: str) -> ToolResult:
        """Write content to file."""
        if not path:
            return ToolResult(success=False, error="Path is required")

        resolved = self._validate_path(path)

        # Create parent directories if needed
        resolved.parent.mkdir(parents=True, exist_ok=True)

        resolved.write_text(content, encoding="utf-8")
        return ToolResult(
            success=True,
            data={
                "path": str(resolved),
                "size": len(content),
            },
        )

    async def _list_directory(self, path: str = ".") -> ToolResult:
        """List directory contents."""
        resolved = self._validate_path(path)

        if not resolved.exists():
            return ToolResult(success=False, error=f"Directory not found: {path}")

        if not resolved.is_dir():
            return ToolResult(success=False, error=f"Not a directory: {path}")

        items = []
        for item in resolved.iterdir():
            items.append({
                "name": item.name,
                "type": "directory" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else None,
                "modified": item.stat().st_mtime,
            })

        return ToolResult(
            success=True,
            data={
                "path": str(resolved),
                "items": items,
                "count": len(items),
            },
        )

    async def _copy(self, source: str, destination: str) -> ToolResult:
        """Copy file or directory."""
        src = self._validate_path(source)
        dst = self._validate_path(destination)

        if not src.exists():
            return ToolResult(success=False, error=f"Source not found: {source}")

        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

        return ToolResult(
            success=True,
            data={"source": str(src), "destination": str(dst)},
        )

    async def _move(self, source: str, destination: str) -> ToolResult:
        """Move file or directory."""
        src = self._validate_path(source)
        dst = self._validate_path(destination)

        if not src.exists():
            return ToolResult(success=False, error=f"Source not found: {source}")

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))

        return ToolResult(
            success=True,
            data={"source": str(src), "destination": str(dst)},
        )

    async def _delete(self, path: str) -> ToolResult:
        """Delete file or directory."""
        resolved = self._validate_path(path)

        if not resolved.exists():
            return ToolResult(success=False, error=f"Path not found: {path}")

        if resolved.is_dir():
            shutil.rmtree(resolved)
        else:
            resolved.unlink()

        return ToolResult(success=True, data={"path": str(resolved)})

    async def _exists(self, path: str) -> ToolResult:
        """Check if path exists."""
        resolved = self._validate_path(path)
        return ToolResult(
            success=True,
            data={"path": str(resolved), "exists": resolved.exists()},
        )

    async def _stats(self, path: str) -> ToolResult:
        """Get file/directory statistics."""
        resolved = self._validate_path(path)

        if not resolved.exists():
            return ToolResult(success=False, error=f"Path not found: {path}")

        stat = resolved.stat()
        return ToolResult(
            success=True,
            data={
                "path": str(resolved),
                "type": "directory" if resolved.is_dir() else "file",
                "size": stat.st_size,
                "created": stat.st_ctime,
                "modified": stat.st_mtime,
                "accessed": stat.st_atime,
                "permissions": oct(stat.st_mode),
            },
        )

    async def _glob(self, pattern: str, path: str = ".") -> ToolResult:
        """Find files matching pattern."""
        base = self._validate_path(path)
        matches = list(base.glob(pattern))

        results = []
        for m in matches:
            results.append({
                "path": str(m),
                "name": m.name,
                "type": "directory" if m.is_dir() else "file",
            })

        return ToolResult(
            success=True,
            data={"pattern": pattern, "matches": results, "count": len(results)},
        )

    async def _search(self, path: str, pattern: str) -> ToolResult:
        """Search for pattern in files (grep-like)."""
        import re

        base = self._validate_path(path)
        regex = re.compile(pattern)
        matches = []

        if base.is_file():
            files = [base]
        else:
            files = [f for f in base.rglob("*") if f.is_file()]

        for f in files:
            try:
                if f.stat().st_size > self.max_file_size:
                    continue
                content = f.read_text(encoding="utf-8", errors="ignore")
                for i, line in enumerate(content.splitlines(), 1):
                    if regex.search(line):
                        matches.append({
                            "file": str(f),
                            "line": i,
                            "content": line.strip(),
                        })
            except Exception:
                continue

        return ToolResult(
            success=True,
            data={"pattern": pattern, "matches": matches, "count": len(matches)},
        )


class TemporaryFileTool(Tool):
    """Tool for temporary file operations."""

    def __init__(self):
        super().__init__(
            name="temp_file",
            description="Create and manage temporary files",
            category=ToolCategory.DATA_ACCESS,
        )
        self._temp_files: dict[str, str] = {}

    async def execute(self, operation: str, **kwargs) -> ToolResult:
        """Execute temporary file operation."""
        try:
            if operation == "create":
                return await self._create_temp(
                    kwargs.get("content", ""),
                    kwargs.get("suffix", ""),
                    kwargs.get("prefix", "scidata_"),
                )
            elif operation == "cleanup":
                return await self._cleanup(kwargs.get("file_id"))
            elif operation == "list":
                return await self._list_temp()
            else:
                return ToolResult(success=False, error=f"Unknown operation: {operation}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _create_temp(
        self,
        content: str,
        suffix: str,
        prefix: str,
    ) -> ToolResult:
        """Create a temporary file."""
        fd, path = tempfile.mkstemp(suffix=suffix, prefix=prefix)
        with os.fdopen(fd, "w") as f:
            f.write(content)

        file_id = hashlib.md5(path.encode()).hexdigest()[:8]
        self._temp_files[file_id] = path

        return ToolResult(
            success=True,
            data={"file_id": file_id, "path": path, "size": len(content)},
        )

    async def _cleanup(self, file_id: str) -> ToolResult:
        """Clean up a temporary file."""
        if file_id not in self._temp_files:
            return ToolResult(success=False, error=f"File ID not found: {file_id}")

        path = self._temp_files.pop(file_id)
        if os.path.exists(path):
            os.unlink(path)

        return ToolResult(success=True, data={"file_id": file_id, "deleted": True})

    async def _list_temp(self) -> ToolResult:
        """List all temporary files."""
        files = []
        for file_id, path in self._temp_files.items():
            if os.path.exists(path):
                files.append({"file_id": file_id, "path": path})
            else:
                self._temp_files.pop(file_id, None)

        return ToolResult(success=True, data={"files": files, "count": len(files)})
