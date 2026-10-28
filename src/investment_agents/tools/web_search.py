from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse

from duckduckgo_search import DDGS
from duckduckgo_search.exceptions import DuckDuckGoSearchException

from investment_agents.tools.base import ToolReadiness, ToolResult


class WebSearchTool:
    """Small web-search adapter that returns source-linked evidence."""

    name = "web_search"

    def __init__(self, max_results: int = 5, timeout_seconds: int = 10) -> None:
        self.max_results = max_results
        self.timeout_seconds = timeout_seconds

    def readiness(self) -> ToolReadiness:
        return ToolReadiness(
            tool_name=self.name,
            configured=True,
            status="ready",
            capabilities=["web_search", "source_citations"],
        )

    def search(self, query: str) -> ToolResult:
        try:
            with DDGS(timeout=self.timeout_seconds) as search_client:
                results = search_client.text(query, max_results=self.max_results)
        except DuckDuckGoSearchException as exc:
            return ToolResult(
                tool_name=self.name,
                status="provider_error",
                summary=f"Web search failed: {exc}",
                data={"query": query, "error_type": type(exc).__name__},
            )

        retrieved_at = datetime.now(timezone.utc).isoformat()
        evidence = []
        for item in results or []:
            title = str(item.get("title", "")).strip()
            url = str(item.get("href", "")).strip()
            snippet = str(item.get("body", "")).strip()
            parsed_url = urlparse(url)
            if not title or parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
                continue
            source = parsed_url.netloc.removeprefix("www.")
            evidence.append(
                {
                    "title": title,
                    "url": url,
                    "source": source,
                    "snippet": snippet,
                    "retrieved_at": retrieved_at,
                    "citation": {
                        "title": title,
                        "url": url,
                        "source": source,
                        "claim": snippet or title,
                        "retrieved_at": retrieved_at,
                    },
                }
            )

        summary = (
            f"Web search found {len(evidence)} source-linked results."
            if evidence
            else "Web search returned no source-linked results."
        )
        return ToolResult(
            tool_name=self.name,
            status="ok" if evidence else "no_results",
            summary=summary,
            data={
                "query": query,
                "results": evidence,
                "citations": [item["citation"] for item in evidence],
                "retrieved_at": retrieved_at,
            },
        )
