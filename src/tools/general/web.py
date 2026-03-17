"""Web 工具 - 移植自 nanobot"""

import html
import json
import os
import re
from typing import Any
from urllib.parse import urlparse

from .base import Tool

# Shared constants
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_2) AppleWebKit/537.36"
MAX_REDIRECTS = 5  # Limit redirects to prevent DoS attacks


def _strip_tags(text: str) -> str:
    """Remove HTML tags and decode entities."""
    text = re.sub(r'<script[\s\S]*?</script>', '', text, flags=re.I)
    text = re.sub(r'<style[\s\S]*?</style>', '', text, flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    return html.unescape(text).strip()


def _normalize(text: str) -> str:
    """Normalize whitespace."""
    text = re.sub(r'[ \t]+', ' ', text)
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def _validate_url(url: str) -> tuple[bool, str]:
    """Validate URL: must be http(s) with valid domain."""
    try:
        p = urlparse(url)
        if p.scheme not in ('http', 'https'):
            return False, f"Only http/https allowed, got '{p.scheme or 'none'}'"
        if not p.netloc:
            return False, "Missing domain"
        return True, ""
    except Exception as e:
        return False, str(e)


class WebSearchTool(Tool):
    """Search the web using Brave Search API."""

    name = "web_search"
    description = "Search the web. Returns titles, URLs, and snippets. Use this when you need up-to-date information."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "count": {"type": "integer", "description": "Results (1-10)", "minimum": 1, "maximum": 10}
        },
        "required": ["query"]
    }

    def __init__(self, api_key: str | None = None, max_results: int = 5, proxy: str | None = None):
        self._init_api_key = api_key
        self.max_results = max_results
        self.proxy = proxy

    @property
    def api_key(self) -> str:
        """Resolve API key at call time so env/config changes are picked up."""
        return self._init_api_key or os.environ.get("BRAVE_API_KEY", "")

    async def execute(self, query: str, count: int | None = None, **kwargs: Any) -> str:
        # 如果没有 Brave API key，尝试使用 DuckDuckGo
        if not self.api_key:
            return await self._ddg_search(query, count)
        
        try:
            import httpx
        except ImportError:
            return "Error: httpx not installed. Install with: pip install httpx"

        try:
            n = min(max(count or self.max_results, 1), 10)
            async with httpx.AsyncClient(proxy=self.proxy) as client:
                r = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query, "count": n},
                    headers={"Accept": "application/json", "X-Subscription-Token": self.api_key},
                    timeout=10.0
                )
                r.raise_for_status()

            results = r.json().get("web", {}).get("results", [])[:n]
            if not results:
                return f"No results for: {query}"

            lines = [f"Results for: {query}\n"]
            for i, item in enumerate(results, 1):
                lines.append(f"{i}. {item.get('title', '')}\n   {item.get('url', '')}")
                if desc := item.get("description"):
                    lines.append(f"   {desc}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    async def _ddg_search(self, query: str, count: int | None = None) -> str:
        """使用 DuckDuckGo Instant Answer API (免费)"""
        import aiohttp
        
        n = min(max(count or self.max_results, 1), 10)
        url = "https://api.duckduckgo.com/"
        
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
                async with session.get(url, params={
                    "q": query,
                    "format": "json",
                    "no_html": 1,
                    "skip_disambig": 1
                }) as r:
                    r.raise_for_status()
                    data = await r.json()
            
            # 获取即时答案
            if data.get("AnswerType") == "calc" or data.get("AbstractText"):
                answer = data.get("AbstractText", "")
                if answer:
                    return f"Answer: {answer}\n\nRelated: {data.get('AbstractURL', '')}"
            
            # 获取相关主题
            results = []
            for topic in data.get("RelatedTopics", [])[:n]:
                if "Text" in topic and "FirstURL" in topic:
                    results.append(f"- {topic['Text']}: {topic['FirstURL']}")
            
            if results:
                return f"Results for '{query}':\n" + "\n".join(results)
            
            return f"No results for: {query}"
            
        except Exception as e:
            return f"Error: {e}"


class WebFetchTool(Tool):
    """Fetch and extract content from a URL using Readability."""

    name = "web_fetch"
    description = "Fetch URL and extract readable content (HTML → markdown/text)."
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch"},
            "extractMode": {"type": "string", "enum": ["markdown", "text"], "default": "markdown"},
            "maxChars": {"type": "integer", "minimum": 100}
        },
        "required": ["url"]
    }

    def __init__(self, max_chars: int = 50000, proxy: str | None = None):
        self.max_chars = max_chars
        self.proxy = proxy

    async def execute(self, url: str, extractMode: str = "markdown", maxChars: int | None = None, **kwargs: Any) -> str:
        import aiohttp
        
        max_chars = maxChars or self.max_chars
        is_valid, error_msg = _validate_url(url)
        if not is_valid:
            return json.dumps({"error": f"URL validation failed: {error_msg}", "url": url}, ensure_ascii=False)

        try:
            timeout = aiohttp.ClientTimeout(total=30)
            connector = aiohttp.TCPConnector(ssl=False)
            text = ""
            ctype = ""
            
            async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
                async with session.get(url, headers={"User-Agent": USER_AGENT}) as r:
                    r.raise_for_status()
                    text = await r.text()
                    ctype = r.headers.get("content-type", "")

            if "application/json" in ctype:
                text, extractor = json.dumps(json.loads(text), indent=2, ensure_ascii=False), "json"
            elif "text/html" in ctype or text[:256].lower().startswith(("<!doctype", "<html")):
                try:
                    from readability import Document
                    doc = Document(text)
                    content = self._to_markdown(doc.summary()) if extractMode == "markdown" else _strip_tags(doc.summary())
                    text = f"# {doc.title()}\n\n{content}" if doc.title() else content
                    extractor = "readability"
                except ImportError:
                    text, extractor = _strip_tags(text), "raw"
            else:
                text, extractor = text, "raw"

            truncated = len(text) > max_chars
            if truncated: text = text[:max_chars]

            return json.dumps({
                "url": url, 
                "status": r.status,
                "extractor": extractor, 
                "truncated": truncated, 
                "length": len(text), 
                "text": text
            }, ensure_ascii=False)
        except aiohttp.ClientError as e:
            return json.dumps({"error": f"Client error: {e}", "url": url}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e), "url": url}, ensure_ascii=False)

    def _to_markdown(self, html: str) -> str:
        """Convert HTML to markdown."""
        # Convert links, headings, lists before stripping tags
        text = re.sub(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>',
                      lambda m: f'[{_strip_tags(m[2])}]({m[1]})', html, flags=re.I)
        text = re.sub(r'<h([1-6])[^>]*>([\s\S]*?)</h\1>',
                      lambda m: f'\n{"#" * int(m[1])} {_strip_tags(m[2])}\n', text, flags=re.I)
        text = re.sub(r'<li[^>]*>([\s\S]*?)</li>', lambda m: f'\n- {_strip_tags(m[1])}', text, flags=re.I)
        text = re.sub(r'</(p|div|section|article)>', '\n\n', text, flags=re.I)
        text = re.sub(r'<(br|hr)\s*/?>', '\n', text, flags=re.I)
        return _normalize(_strip_tags(text))


class BrowserTool(Tool):
    """Browser automation tool using Playwright."""

    name = "browser"
    description = "Browser automation with Playwright - screenshot, click, fill, evaluate"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": ["screenshot", "click", "fill", "evaluate"]},
                "url": {"type": "string", "description": "URL to interact with"},
                "selector": {"type": "string", "description": "CSS selector"},
                "value": {"type": "string", "description": "Value to fill (for fill operation)"},
                "script": {"type": "string", "description": "JavaScript to evaluate (for evaluate operation)"}
            },
            "required": ["operation", "url"]
        }

    async def execute(self, operation: str, url: str, selector: str = None, value: str = None, script: str = None, **kwargs) -> str:
        """Execute browser operation."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return json.dumps({"error": "Playwright not installed. Install with: pip install playwright"})

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                page = await browser.new_page()
                await page.goto(url)

                if operation == "screenshot":
                    if selector:
                        element = await page.query_selector(selector)
                        if element:
                            screenshot = await element.screenshot()
                        else:
                            return json.dumps({"error": "Selector not found"})
                    else:
                        screenshot = await page.screenshot()
                    import base64
                    b64 = base64.b64encode(screenshot).decode()
                    return json.dumps({"url": url, "screenshot": f"data:image/png;base64,{b64}"})

                elif operation == "click":
                    if not selector:
                        return json.dumps({"error": "selector required for click"})
                    await page.click(selector)
                    await browser.close()
                    return json.dumps({"clicked": selector})

                elif operation == "fill":
                    if not selector or not value:
                        return json.dumps({"error": "selector and value required for fill"})
                    await page.fill(selector, value)
                    await browser.close()
                    return json.dumps({"filled": selector, "value": value})

                elif operation == "evaluate":
                    if not script:
                        return json.dumps({"error": "script required for evaluate"})
                    result = await page.evaluate(script)
                    await browser.close()
                    return json.dumps({"result": result})

                await browser.close()
                return json.dumps({"error": f"Unknown operation: {operation}"})

        except Exception as e:
            return json.dumps({"error": str(e)})
