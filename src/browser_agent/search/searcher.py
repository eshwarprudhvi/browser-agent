import os
from dataclasses import dataclass
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()


class SearchError(Exception):
    """Raised when a web search cannot be completed or configured."""
    pass


@dataclass
class SearchResult:
    """Represents a standardized search result."""
    url: str
    title: str = ""
    content: str = ""
    score: float = 0.0


class WebSearcher:
    """
    Isolated web search component.
    Uses Tavily as the primary search engine, with DuckDuckGo as automatic fallback.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("TAVILY_API_KEY")

    def _search_tavily(self, query: str, max_results: int = 5) -> List[SearchResult]:
        """Executes search via Tavily."""
        if not self.api_key:
            raise SearchError("TAVILY_API_KEY is not configured.")

        from tavily import TavilyClient

        client = TavilyClient(api_key=self.api_key)
        response = client.search(query=query, max_results=max_results)
        raw_results = response.get("results", [])

        results: List[SearchResult] = []
        for item in raw_results:
            url = item.get("url")
            if url:
                results.append(
                    SearchResult(
                        url=url,
                        title=item.get("title", ""),
                        content=item.get("content", ""),
                        score=float(item.get("score", 0.0)),
                    )
                )

        return results

    def _search_duckduckgo(self, query: str, max_results: int = 5) -> List[SearchResult]:
        """Executes search via DuckDuckGo as a fallback."""
        try:
            try:
                from ddgs import DDGS
            except ImportError:
                from duckduckgo_search import DDGS

            ddgs = DDGS()
            raw_results = ddgs.text(query, max_results=max_results)
            if not raw_results:
                raw_results = ddgs.text(query, backend="html", max_results=max_results)

            results: List[SearchResult] = []
            for item in raw_results or []:
                url = item.get("href")
                if url:
                    results.append(
                        SearchResult(
                            url=url,
                            title=item.get("title", ""),
                            content=item.get("body", ""),
                            score=0.7,
                        )
                    )

            return results
        except Exception as e:
            raise SearchError(f"DuckDuckGo search failed: {e}") from e

    def search(self, query: str, max_results: int = 5) -> List[SearchResult]:
        """
        Executes web search. Attempts Tavily first, and automatically falls back
        to DuckDuckGo if Tavily is unavailable, unconfigured, or fails.
        """
        tavily_error: Optional[Exception] = None

        # 1. Attempt Tavily if API key is present
        if self.api_key:
            try:
                results = self._search_tavily(query, max_results=max_results)
                if results:
                    return results
            except Exception as e:
                tavily_error = e

        # 2. Fall back to DuckDuckGo
        try:
            ddg_results = self._search_duckduckgo(query, max_results=max_results)
            if ddg_results:
                return ddg_results
        except Exception as ddg_err:
            if tavily_error:
                raise SearchError(
                    f"Tavily search failed ({tavily_error}) and DuckDuckGo fallback also failed ({ddg_err})"
                ) from ddg_err
            raise

        if tavily_error:
            raise SearchError(f"Tavily search failed ({tavily_error}) and DuckDuckGo returned no results.")

        return []
