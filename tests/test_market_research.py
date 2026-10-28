from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from duckduckgo_search.exceptions import DuckDuckGoSearchException

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
for path in (ROOT_DIR, SRC_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from investment_agents.agents.orchestrator import OrchestratorAgent
from investment_agents.core.config import Settings
from investment_agents.domain.currencies import extract_currency_codes
from investment_agents.domain.tickers import extract_ticker_symbols
from investment_agents.tools.base import ToolResult
from investment_agents.tools.web_search import WebSearchTool


class CurrencyRoutingTests(unittest.TestCase):
    def test_currency_codes_are_not_mistaken_for_tickers(self) -> None:
        question = "What are the current market trends around the USD?"

        self.assertEqual(extract_currency_codes(question), ["USD"])
        self.assertEqual(extract_ticker_symbols(question), [])
        self.assertEqual(extract_currency_codes("How is the US dollar moving?"), ["USD"])

    def test_usd_trends_use_fx_macro_and_web_agents_with_citations(self) -> None:
        forex_response = Mock()
        forex_response.json.return_value = {
            "base": "USD",
            "quote": {"EUR": 0.92, "JPY": 150.1},
        }
        news_response = Mock()
        news_response.json.return_value = {
            "feed": [
                {
                    "title": "Central bank outlook",
                    "url": "https://news.example/central-bank",
                    "source": "Example News",
                    "time_published": "20261028T100000",
                    "overall_sentiment_label": "Neutral",
                }
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings(
                finnhub_api_key="test-key",
                alphavantage_api_key="test-key",
                storage_db_path=str(Path(temp_dir) / "market.duckdb"),
            )
            agent = OrchestratorAgent.from_settings(settings)
            agent.finnhub_agent.tool.cache = None
            agent.alphavantage_agent.tool.cache = None
            agent.web_search_agent.tool.search = lambda query: ToolResult(
                tool_name="web_search",
                summary="Web search found 1 source-linked result.",
                data={
                    "query": query,
                    "results": [
                        {
                            "title": "Dollar market outlook",
                            "snippet": "The dollar moved as bond yields shifted.",
                        }
                    ],
                    "citations": [
                        {
                            "title": "Dollar market outlook",
                            "url": "https://markets.example/usd",
                            "source": "markets.example",
                            "claim": "The dollar moved as bond yields shifted.",
                            "retrieved_at": "2026-10-28T10:00:00+00:00",
                        }
                    ],
                },
            )

            def provider_response(url: str, **kwargs):
                return forex_response if "/forex/rates" in url else news_response

            with patch(
                "investment_agents.tools.finnhub.requests.get",
                side_effect=provider_response,
            ) as provider_get:
                forex_response.raise_for_status.return_value = None
                news_response.raise_for_status.return_value = None
                response = agent.respond(
                    "What are the current market trends around the USD?"
                )

        self.assertEqual(
            response.selected_agents,
            [
                "finnhub_investment_agent",
                "alphavantage_research_agent",
                "web_search_agent",
            ],
        )
        self.assertEqual(response.routing_decision["currency_codes"], ["USD"])
        self.assertEqual(response.routing_decision["symbols"], [])
        self.assertEqual(provider_get.call_count, 2)
        forex_call, news_call = provider_get.call_args_list
        self.assertEqual(forex_call.kwargs["params"]["base"], "USD")
        self.assertEqual(news_call.kwargs["params"]["function"], "NEWS_SENTIMENT")
        self.assertGreaterEqual(len(response.citations), 4)
        self.assertIn("1 USD = 0.92 EUR", response.reply)
        self.assertIn("Central bank outlook", response.reply)
        self.assertIn("https://markets.example/usd", response.reply)


class WebSearchTests(unittest.TestCase):
    def test_search_results_include_claims_and_source_links(self) -> None:
        client = MagicMock()
        client.__enter__.return_value.text.return_value = [
            {
                "title": "Dollar outlook",
                "href": "https://markets.example/dollar",
                "body": "The dollar strengthened.",
            }
        ]

        with patch("investment_agents.tools.web_search.DDGS", return_value=client):
            result = WebSearchTool().search("USD market trends")

        citation = result.data["citations"][0]
        self.assertEqual(result.status, "ok")
        self.assertEqual(citation["claim"], "The dollar strengthened.")
        self.assertEqual(citation["source"], "markets.example")
        self.assertEqual(citation["url"], "https://markets.example/dollar")

    def test_search_failures_are_reported_as_provider_errors(self) -> None:
        with patch(
            "investment_agents.tools.web_search.DDGS",
            side_effect=DuckDuckGoSearchException("search unavailable"),
        ):
            result = WebSearchTool().search("USD market trends")

        self.assertEqual(result.status, "provider_error")
        self.assertIn("search failed", result.summary.lower())


if __name__ == "__main__":
    unittest.main()
