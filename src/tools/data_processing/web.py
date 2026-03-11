"""Web scraping and browser control tools."""
import asyncio
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import aiohttp

from src.tools.base import Tool, ToolResult, ToolCategory


class WebTool(Tool):
    """Tool for web scraping and HTTP operations."""

    def __init__(
        self,
        timeout: int = 30,
        max_redirects: int = 5,
        headers: Optional[Dict[str, str]] = None,
    ):
        """Initialize web tool.

        Args:
            timeout: Request timeout in seconds.
            max_redirects: Maximum number of redirects.
            headers: Default headers for requests.
        """
        super().__init__(
            name="web",
            description="Web scraping, HTTP requests, and browser-like operations",
            category=ToolCategory.DATA_ACCESS,
        )
        self.timeout = timeout
        self.max_redirects = max_redirects
        self.default_headers = headers or {
            "User-Agent": "Mozilla/5.0 (compatible; SciDataBot/1.0)",
        }

    async def execute(self, operation: str, **kwargs) -> ToolResult:
        """Execute web operation."""
        try:
            if operation == "get":
                return await self._get(
                    kwargs.get("url"),
                    params=kwargs.get("params"),
                    headers=kwargs.get("headers"),
                )
            elif operation == "post":
                return await self._post(
                    kwargs.get("url"),
                    data=kwargs.get("data"),
                    json=kwargs.get("json"),
                    headers=kwargs.get("headers"),
                )
            elif operation == "scrape":
                return await self._scrape(
                    kwargs.get("url"),
                    selectors=kwargs.get("selectors"),
                    headers=kwargs.get("headers"),
                )
            elif operation == "extract_links":
                return await self._extract_links(kwargs.get("url"))
            elif operation == "screenshot":
                return await self._screenshot(kwargs.get("url"))
            else:
                return ToolResult(success=False, error=f"Unknown operation: {operation}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _get(
        self,
        url: str,
        params: Optional[Dict[str, str]],
        headers: Optional[Dict[str, str]],
    ) -> ToolResult:
        """Perform GET request."""
        if not url:
            return ToolResult(success=False, error="URL is required")

        request_headers = self.default_headers.copy()
        if headers:
            request_headers.update(headers)

        timeout = aiohttp.ClientTimeout(total=self.timeout)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                url,
                params=params,
                headers=request_headers,
                allow_redirects=True,
            ) as response:
                content = await response.text()

                return ToolResult(
                    success=True,
                    data={
                        "url": str(response.url),
                        "status": response.status,
                        "headers": dict(response.headers),
                        "content": content[:100000],  # Limit content size
                        "content_type": response.content_type,
                    },
                )

    async def _post(
        self,
        url: str,
        data: Optional[Dict],
        json: Optional[Dict],
        headers: Optional[Dict[str, str]],
    ) -> ToolResult:
        """Perform POST request."""
        if not url:
            return ToolResult(success=False, error="URL is required")

        request_headers = self.default_headers.copy()
        if headers:
            request_headers.update(headers)

        timeout = aiohttp.ClientTimeout(total=self.timeout)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                url,
                data=data,
                json=json,
                headers=request_headers,
            ) as response:
                content = await response.text()

                return ToolResult(
                    success=True,
                    data={
                        "url": str(response.url),
                        "status": response.status,
                        "headers": dict(response.headers),
                        "content": content[:100000],
                    },
                )

    async def _scrape(
        self,
        url: str,
        selectors: Optional[List[str]],
        headers: Optional[Dict[str, str]],
    ) -> ToolResult:
        """Scrape web page with CSS selectors."""
        if not url:
            return ToolResult(success=False, error="URL is required")

        # First get the page content
        result = await self._get(url, None, headers)
        if not result.success:
            return result

        content = result.data["content"]

        # Try to parse with BeautifulSoup if available
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(content, "html.parser")

            if selectors:
                extracted = {}
                for selector in selectors:
                    elements = soup.select(selector)
                    extracted[selector] = [
                        elem.get_text(strip=True) for elem in elements
                    ]
                return ToolResult(
                    success=True,
                    data={
                        "url": url,
                        "extracted": extracted,
                    },
                )
            else:
                # Return basic info
                return ToolResult(
                    success=True,
                    data={
                        "url": url,
                        "title": soup.title.string if soup.title else None,
                        "links": [
                            a.get("href")
                            for a in soup.find_all("a", href=True)
                        ][:20],
                        "text": soup.get_text()[:5000],
                    },
                )

        except ImportError:
            # Fallback to regex-based extraction
            return ToolResult(
                success=True,
                data={
                    "url": url,
                    "content": content[:100000],
                    "message": "BeautifulSoup not installed, returning raw content",
                },
            )

    async def _extract_links(self, url: str) -> ToolResult:
        """Extract all links from a webpage."""
        result = await self._get(url, None, None)
        if not result.success:
            return result

        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(result.data["content"], "html.parser")
            base_url = urlparse(url)

            links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                # Resolve relative URLs
                full_url = urljoin(url, href)
                links.append(full_url)

            # Remove duplicates while preserving order
            unique_links = list(dict.fromkeys(links))

            return ToolResult(
                success=True,
                data={
                    "url": url,
                    "links": unique_links,
                    "count": len(unique_links),
                },
            )

        except ImportError:
            # Fallback to regex
            import re

            hrefs = re.findall(r'href=["\']([^"\']+)["\']', result.data["content"])
            links = [urljoin(url, href) for href in hrefs]

            return ToolResult(
                success=True,
                data={
                    "url": url,
                    "links": list(dict.fromkeys(links)),
                    "count": len(links),
                },
            )

    async def _screenshot(self, url: str) -> ToolResult:
        """Take a screenshot of a webpage."""
        # This would require a browser automation tool like Playwright
        # For now, return a message about what's needed
        return ToolResult(
            success=False,
            error="Screenshot requires Playwright. Install with: pip install playwright && playwright install chromium",
        )


class BrowserTool(Tool):
    """Browser automation tool using Playwright."""

    def __init__(self):
        super().__init__(
            name="browser",
            description="Browser automation with Playwright",
            category=ToolCategory.DATA_ACCESS,
        )

    async def execute(self, operation: str, **kwargs) -> ToolResult:
        """Execute browser operation."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return ToolResult(
                success=False,
                error="Playwright not installed. Install with: pip install playwright",
            )

        try:
            if operation == "screenshot":
                return await self._screenshot(
                    kwargs.get("url"),
                    kwargs.get("selector"),
                )
            elif operation == "click":
                return await self._click(
                    kwargs.get("url"),
                    kwargs.get("selector"),
                )
            elif operation == "fill":
                return await self._fill(
                    kwargs.get("url"),
                    kwargs.get("selector"),
                    kwargs.get("value"),
                )
            elif operation == "evaluate":
                return await self._evaluate(
                    kwargs.get("url"),
                    kwargs.get("script"),
                )
            else:
                return ToolResult(success=False, error=f"Unknown operation: {operation}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _screenshot(self, url: str, selector: Optional[str]) -> ToolResult:
        """Take a screenshot."""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(url)

            if selector:
                element = await page.query_selector(selector)
                if element:
                    screenshot = await element.screenshot()
                else:
                    return ToolResult(success=False, error="Selector not found")
            else:
                screenshot = await page.screenshot()

            await browser.close()

            import base64
            b64 = base64.b64encode(screenshot).decode()

            return ToolResult(
                success=True,
                data={
                    "url": url,
                    "screenshot": f"data:image/png;base64,{b64}",
                },
            )

    async def _click(self, url: str, selector: str) -> ToolResult:
        """Click an element."""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(url)

            await page.click(selector)
            await browser.close()

            return ToolResult(success=True, data={"clicked": selector})

    async def _fill(self, url: str, selector: str, value: str) -> ToolResult:
        """Fill a form field."""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(url)

            await page.fill(selector, value)
            await browser.close()

            return ToolResult(success=True, data={"filled": selector})

    async def _evaluate(self, url: str, script: str) -> ToolResult:
        """Evaluate JavaScript in page context."""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(url)

            result = await page.evaluate(script)
            await browser.close()

            return ToolResult(success=True, data={"result": result})
