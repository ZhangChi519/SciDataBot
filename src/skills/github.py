"""GitHub integration skill."""
import asyncio
from typing import Any, Dict, List, Optional

from src.tools.base import Tool, ToolResult, ToolCategory


class GitHubSkill(Tool):
    """Skill for GitHub integration."""

    name = "github"
    description = "GitHub repository operations, issues, PRs"
    category = ToolCategory.DATA_ACCESS

    def __init__(self, token: Optional[str] = None):
        """Initialize GitHub skill."""
        self.token = token

    async def execute(self, operation: str, **kwargs) -> ToolResult:
        """Execute GitHub operation."""
        try:
            if operation == "search_repos":
                return await self._search_repos(kwargs.get("query"))
            elif operation == "get_repo":
                return await self._get_repo(kwargs.get("owner"), kwargs.get("repo"))
            elif operation == "list_issues":
                return await self._list_issues(
                    kwargs.get("owner"),
                    kwargs.get("repo"),
                    kwargs.get("state", "open"),
                )
            elif operation == "create_issue":
                return await self._create_issue(
                    kwargs.get("owner"),
                    kwargs.get("repo"),
                    kwargs.get("title"),
                    kwargs.get("body"),
                )
            elif operation == "list_prs":
                return await self._list_prs(
                    kwargs.get("owner"),
                    kwargs.get("repo"),
                    kwargs.get("state", "open"),
                )
            else:
                return ToolResult(success=False, error=f"Unknown operation: {operation}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _make_request(
        self,
        method: str,
        url: str,
        data: Optional[Dict] = None,
    ) -> Dict:
        """Make GitHub API request."""
        import aiohttp

        headers = {
            "Accept": "application/vnd.github.v3+json",
        }
        if self.token:
            headers["Authorization"] = f"token {self.token}"

        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, json=data, headers=headers) as response:
                if response.status == 204:
                    return {"success": True}

                result = await response.json()

                if response.status >= 400:
                    raise Exception(f"GitHub API error: {result.get('message', 'Unknown error')}")

                return result

    async def _search_repos(self, query: str) -> ToolResult:
        """Search repositories."""
        url = f"https://api.github.com/search/repositories?q={query}"
        result = await self._make_request("GET", url)

        repos = []
        for item in result.get("items", [])[:10]:
            repos.append({
                "name": item.get("name"),
                "full_name": item.get("full_name"),
                "description": item.get("description"),
                "stars": item.get("stargazers_count"),
                "language": item.get("language"),
                "url": item.get("html_url"),
            })

        return ToolResult(success=True, data={"repos": repos, "count": len(repos)})

    async def _get_repo(self, owner: str, repo: str) -> ToolResult:
        """Get repository info."""
        url = f"https://api.github.com/repos/{owner}/{repo}"
        result = await self._make_request("GET", url)

        return ToolResult(
            success=True,
            data={
                "name": result.get("name"),
                "full_name": result.get("full_name"),
                "description": result.get("description"),
                "stars": result.get("stargazers_count"),
                "forks": result.get("forks_count"),
                "language": result.get("language"),
                "default_branch": result.get("default_branch"),
                "url": result.get("html_url"),
            },
        )

    async def _list_issues(
        self,
        owner: str,
        repo: str,
        state: str,
    ) -> ToolResult:
        """List repository issues."""
        url = f"https://api.github.com/repos/{owner}/{repo}/issues?state={state}"
        result = await self._make_request("GET", url)

        issues = []
        for item in result[:20]:  # Limit to 20
            if "pull_request" not in item:  # Skip PRs
                issues.append({
                    "number": item.get("number"),
                    "title": item.get("title"),
                    "state": item.get("state"),
                    "user": item.get("user", {}).get("login"),
                    "created_at": item.get("created_at"),
                    "url": item.get("html_url"),
                })

        return ToolResult(success=True, data={"issues": issues, "count": len(issues)})

    async def _create_issue(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
    ) -> ToolResult:
        """Create an issue."""
        if not self.token:
            return ToolResult(success=False, error="GitHub token required")

        url = f"https://api.github.com/repos/{owner}/{repo}/issues"
        result = await self._make_request(
            "POST",
            url,
            {"title": title, "body": body},
        )

        return ToolResult(
            success=True,
            data={
                "number": result.get("number"),
                "url": result.get("html_url"),
            },
        )

    async def _list_prs(
        self,
        owner: str,
        repo: str,
        state: str,
    ) -> ToolResult:
        """List pull requests."""
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls?state={state}"
        result = await self._make_request("GET", url)

        prs = []
        for item in result[:20]:
            prs.append({
                "number": item.get("number"),
                "title": item.get("title"),
                "state": item.get("state"),
                "user": item.get("user", {}).get("login"),
                "created_at": item.get("created_at"),
                "url": item.get("html_url"),
            })

        return ToolResult(success=True, data={"prs": prs, "count": len(prs)})
