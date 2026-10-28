from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
for path in (ROOT_DIR, SRC_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


class TickerExtractionTests(unittest.TestCase):
    def test_extracts_uppercase_ticker_without_lowercase_noise(self) -> None:
        from investment_agents.domain.tickers import extract_ticker_symbols

        self.assertEqual(
            extract_ticker_symbols("Review my portfolio loss and AAPL news sentiment"),
            ["AAPL"],
        )

    def test_deduplicates_symbols(self) -> None:
        from investment_agents.domain.tickers import extract_ticker_symbols

        self.assertEqual(extract_ticker_symbols("Compare AAPL with MSFT and AAPL"), ["AAPL", "MSFT"])


class OrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["FINNHUB_API_KEY"] = ""
        os.environ["ALPHAVANTAGE_API_KEY"] = ""
        os.environ["GOOGLE_LEDGER_SHEET_ID"] = ""
        os.environ["GOOGLE_SERVICE_ACCOUNT_FILE"] = ""
        os.environ["GOOGLE_WATCHLIST_RANGE"] = ""

    def test_routes_portfolio_ticker_news_question_to_all_specialists(self) -> None:
        from investment_agents.agents.orchestrator import OrchestratorAgent
        from investment_agents.core.config import get_settings
        from investment_agents.core.observability import event_recorder
        from investment_agents.tools.base import ToolResult
        from investment_agents.tools.web_search import WebSearchTool

        event_recorder.clear()
        orchestrator = OrchestratorAgent.from_settings(get_settings())
        with patch.object(
            WebSearchTool,
            "search",
            return_value=ToolResult(
                tool_name="web_search",
                summary="No web references in this test.",
                data={"citations": []},
            ),
        ):
            response = orchestrator.respond(
                "Review my portfolio loss and AAPL news sentiment"
            )

        self.assertEqual(
            response.selected_agents,
            [
                "ledger_interpretation_agent",
                "finnhub_investment_agent",
                "alphavantage_research_agent",
                "web_search_agent",
            ],
        )
        self.assertEqual(response.routing_decision["symbols"], ["AAPL"])
        self.assertEqual(response.routing_decision["focus_areas"], ["ledger", "market", "research"])

        events = event_recorder.list_events(trace_id=response.trace_id)
        event_types = [event["event_type"] for event in events]
        self.assertIn("orchestrator_decision", event_types)
        self.assertIn("tool_called", event_types)

    def test_derives_watchlist_symbols_for_research_agent(self) -> None:
        from investment_agents.agents.orchestrator import OrchestratorAgent
        from investment_agents.core.config import Settings
        from investment_agents.core.observability import event_recorder
        from investment_agents.tools.base import ToolResult
        from investment_agents.tools.registry import ToolRegistry

        settings = Settings(
            google_ledger_sheet_id="sheet-id",
            google_ledger_range="'USD Holdings Portfolio'!A:Z",
            google_watchlist_range="'Sheet10'!A:Z",
            google_service_account_file="service-account.json",
            max_enrichment_symbols=2,
        )
        registry = ToolRegistry.from_settings(settings)
        holdings_rows = [
            ["Ticker", "Shares held", "Current value", "Currency"],
            ["AMD", "10", "1600", "USD"],
        ]
        watchlist_rows = [
            ["Ticker", "Company", "Exchange", "Status"],
            ["NVDA", "Nvidia", "NASDAQ", "researching"],
            ["SHEL", "Shell", "LON", "watching"],
            ["BARC", "Barclays", "LON", "watching"],
        ]

        def mocked_fetch_rows(range_name=None):
            if range_name == settings.google_watchlist_range:
                return watchlist_rows
            return holdings_rows

        event_recorder.clear()
        orchestrator = OrchestratorAgent.from_tool_registry(registry)
        with patch.object(registry.ledger, "fetch_rows", side_effect=mocked_fetch_rows), patch.object(
            registry.web_search,
            "search",
            return_value=ToolResult(
                tool_name="web_search",
                summary="No web references in this test.",
                data={"citations": []},
            ),
        ):
            response = orchestrator.respond("Research my watchlist")

        self.assertEqual(
            response.selected_agents,
            [
                "ledger_interpretation_agent",
                "alphavantage_research_agent",
                "web_search_agent",
            ],
        )
        research_result = response.agent_results[1]
        self.assertEqual(research_result["metadata"]["symbols"], ["BARC", "NVDA"])
        self.assertNotEqual(research_result["metadata"]["symbols"], ["AAPL"])

        events = event_recorder.list_events(trace_id=response.trace_id)
        event_types = [event["event_type"] for event in events]
        self.assertIn("symbol_context_derived", event_types)

    def test_synthesized_reply_calls_out_stale_provider_sources(self) -> None:
        from investment_agents.agents.base import AgentResult
        from investment_agents.agents.orchestrator import OrchestratorAgent, _source_status_notes
        from investment_agents.core.config import Settings
        from investment_agents.domain.models import RouteDecision

        orchestrator = OrchestratorAgent.from_settings(Settings())
        result = AgentResult(
            agent_name="finnhub_investment_agent",
            task="finnhub_investment_analysis",
            summary="Finnhub is unavailable; using stale cached quote.",
            tool_calls=[
                {
                    "tool_name": "finnhub_investment_data",
                    "status": "stale_cache",
                    "summary": "Finnhub is unavailable; using stale cached quote.",
                    "data": {
                        "symbol": "BARC",
                        "provider_symbol": "LON:BARC",
                        "cache_status": "stale",
                        "stale_fetched_at": "2026-01-01T00:00:00+00:00",
                        "degraded_from": {"status": "rate_limited"},
                    },
                }
            ],
        )
        route = RouteDecision(
            selected_agents=["finnhub_investment_agent"],
            focus_areas=["market"],
            symbols=["BARC"],
        )

        reply = orchestrator._synthesize("Check BARC", [result], "trace-stale", route)

        self.assertIn("Data limitations:", reply)
        self.assertIn(
            "finnhub_investment_agent/finnhub_investment_data BARC (LON:BARC): "
            "using stale cached data from 2026-01-01T00:00:00+00:00 after rate limited.",
            reply,
        )
        source_notes = _source_status_notes([result])
        self.assertEqual(source_notes[0].to_dict()["status"], "stale_cache")
        self.assertEqual(source_notes[0].to_dict()["symbol"], "BARC")
        self.assertEqual(source_notes[0].to_dict()["provider_symbol"], "LON:BARC")
        self.assertEqual(source_notes[0].to_dict()["fetched_at"], "2026-01-01T00:00:00+00:00")
        self.assertEqual(source_notes[0].to_dict()["degraded_from_status"], "rate_limited")


class SettingsAndToolReadinessTests(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ["FINNHUB_API_KEY"] = ""
        os.environ["ALPHAVANTAGE_API_KEY"] = ""
        os.environ["GOOGLE_LEDGER_SHEET_ID"] = ""
        os.environ["GOOGLE_SERVICE_ACCOUNT_FILE"] = ""
        os.environ["GOOGLE_WATCHLIST_RANGE"] = ""
        os.environ["STATIC_FX_RATES"] = ""
        os.environ["REPORTING_CURRENCY"] = ""
        os.environ["FINNHUB_SYMBOL_ALIASES"] = ""
        os.environ["ALPHAVANTAGE_SYMBOL_ALIASES"] = ""
        os.environ["CONCENTRATION_ALERT_THRESHOLD"] = ""
        os.environ["LOSS_ALERT_THRESHOLD"] = ""

    def test_settings_read_environment_at_instantiation_time(self) -> None:
        from investment_agents.core.config import get_settings

        os.environ["FINNHUB_API_KEY"] = ""
        self.assertIsNone(get_settings().finnhub_api_key)

        os.environ["FINNHUB_API_KEY"] = "test-key"
        self.assertEqual(get_settings().finnhub_api_key, "test-key")

    def test_settings_load_local_dotenv_file(self) -> None:
        from investment_agents.core.config import get_settings

        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp_dir:
            dotenv_path = Path(tmp_dir) / ".env"
            dotenv_path.write_text(
                "FINNHUB_API_KEY=dotenv-finnhub\n"
                "ALPHAVANTAGE_API_KEY=dotenv-alpha\n",
                encoding="utf-8",
            )
            try:
                os.chdir(tmp_dir)
                os.environ.pop("FINNHUB_API_KEY", None)
                os.environ.pop("ALPHAVANTAGE_API_KEY", None)

                settings = get_settings()
            finally:
                os.chdir(original_cwd)

        self.assertEqual(settings.finnhub_api_key, "dotenv-finnhub")
        self.assertEqual(settings.alphavantage_api_key, "dotenv-alpha")

    def test_settings_parse_static_fx_rates(self) -> None:
        from investment_agents.core.config import get_settings

        os.environ["REPORTING_CURRENCY"] = "GBP"
        os.environ["STATIC_FX_RATES"] = "USD=0.79,ZAR:0.044"
        os.environ["GOOGLE_WATCHLIST_RANGE"] = "'Sheet10'!A:Z"
        os.environ["FINNHUB_SYMBOL_ALIASES"] = "BARC=LON:BARC,NPN=JSE:NPN"
        os.environ["ALPHAVANTAGE_SYMBOL_ALIASES"] = "BARC=BARC.LON,NPN=NPN.JOH"
        os.environ["CONCENTRATION_ALERT_THRESHOLD"] = "0.50"
        os.environ["LOSS_ALERT_THRESHOLD"] = "0.15"

        settings = get_settings()

        self.assertEqual(settings.reporting_currency, "GBP")
        self.assertEqual(settings.static_fx_rates, {"USD": "0.79", "ZAR": "0.044"})
        self.assertEqual(settings.google_watchlist_range, "'Sheet10'!A:Z")
        self.assertEqual(settings.max_enrichment_symbols, 3)
        self.assertEqual(str(settings.concentration_alert_threshold), "0.50")
        self.assertEqual(str(settings.loss_alert_threshold), "0.15")
        self.assertEqual(settings.finnhub_symbol_aliases["BARC"], "LON:BARC")
        self.assertEqual(settings.alphavantage_symbol_aliases["NPN"], "NPN.JOH")

    def test_tool_registry_reports_missing_configuration_without_secrets(self) -> None:
        from investment_agents.core.config import get_settings
        from investment_agents.tools.registry import ToolRegistry

        os.environ["FINNHUB_API_KEY"] = "secret-finnhub-key"
        os.environ["ALPHAVANTAGE_API_KEY"] = ""
        os.environ["GOOGLE_LEDGER_SHEET_ID"] = ""
        os.environ["GOOGLE_SERVICE_ACCOUNT_FILE"] = ""

        registry = ToolRegistry.from_settings(get_settings())
        readiness = {item["tool_name"]: item for item in registry.readiness_dicts()}

        self.assertTrue(readiness["finnhub_investment_data"]["configured"])
        self.assertFalse(readiness["alphavantage_research"]["configured"])
        self.assertIn("ALPHAVANTAGE_API_KEY", readiness["alphavantage_research"]["missing_settings"])
        self.assertNotIn("secret-finnhub-key", str(readiness))

    def test_first_agent_cli_exports_orchestrator_entrypoint(self) -> None:
        import first_agent

        self.assertTrue(callable(first_agent.main))
        self.assertTrue(callable(first_agent.run_orchestrator_cli))
        self.assertTrue(callable(first_agent.run_local_llm_cli))


class LedgerParsingTests(unittest.TestCase):
    def test_parses_rows_into_cash_flow_and_positions(self) -> None:
        from investment_agents.domain.ledger import parse_ledger_rows, summarize_transactions

        rows = [
            ["Date", "Ticker", "Action", "Shares", "Price", "Fees"],
            ["2026-01-01", "AAPL", "BUY", "10", "100", "1.50"],
            ["2026-01-10", "AAPL", "SELL", "4", "120", "1.00"],
            ["2026-01-11", "MSFT", "BUY", "2", "300", "0"],
        ]

        transactions, warnings = parse_ledger_rows(rows)
        summary = summarize_transactions(transactions, warnings)
        positions = {position.symbol: position for position in summary.positions}

        self.assertEqual(summary.transaction_count, 3)
        self.assertEqual(summary.symbols, ["AAPL", "MSFT"])
        self.assertEqual(str(summary.total_fees), "2.50")
        self.assertEqual(str(positions["AAPL"].quantity), "6")
        self.assertEqual(str(positions["AAPL"].net_cash_flow), "-522.50")
        self.assertEqual(str(positions["MSFT"].quantity), "2")

    def test_keeps_cash_flow_separate_by_currency(self) -> None:
        from investment_agents.domain.ledger import parse_ledger_rows, summarize_transactions

        rows = [
            ["Date", "Ticker", "Action", "Shares", "Price", "Fees", "Currency"],
            ["2026-01-01", "AAPL", "BUY", "1", "100", "1", "USD"],
            ["2026-01-02", "BARC", "BUY", "2", "150", "2", "GBP"],
        ]

        transactions, warnings = parse_ledger_rows(rows)
        summary = summarize_transactions(transactions, warnings)

        self.assertEqual(summary.currencies, ["GBP", "USD"])
        self.assertEqual(str(summary.net_cash_flow_by_currency["USD"]), "-101")
        self.assertEqual(str(summary.net_cash_flow_by_currency["GBP"]), "-302")

    def test_normalizes_cash_flow_to_reporting_currency_when_rates_exist(self) -> None:
        from investment_agents.domain.ledger import parse_ledger_rows, summarize_transactions

        rows = [
            ["Date", "Ticker", "Action", "Shares", "Price", "Fees", "Currency"],
            ["2026-01-01", "AAPL", "BUY", "1", "100", "1", "USD"],
            ["2026-01-02", "BARC", "BUY", "2", "150", "2", "GBP"],
        ]

        transactions, warnings = parse_ledger_rows(rows)
        summary = summarize_transactions(
            transactions,
            warnings,
            reporting_currency="USD",
            fx_rates={"GBP": "1.25"},
        )

        self.assertEqual(summary.reporting_currency, "USD")
        self.assertEqual(str(summary.net_cash_flow_reporting_currency), "-478.50")
        self.assertEqual(str(summary.total_fees_reporting_currency), "3.50")
        self.assertEqual(summary.missing_fx_rates, [])

    def test_reports_missing_fx_rates_without_normalized_total(self) -> None:
        from investment_agents.domain.ledger import parse_ledger_rows, summarize_transactions

        rows = [
            ["Date", "Ticker", "Action", "Shares", "Price", "Fees", "Currency"],
            ["2026-01-02", "BARC", "BUY", "2", "150", "2", "GBP"],
        ]

        transactions, warnings = parse_ledger_rows(rows)
        summary = summarize_transactions(transactions, warnings, reporting_currency="USD")

        self.assertIsNone(summary.net_cash_flow_reporting_currency)
        self.assertEqual(summary.missing_fx_rates, ["GBP->USD"])

    def test_reports_missing_required_columns(self) -> None:
        from investment_agents.domain.ledger import parse_ledger_rows

        transactions, warnings = parse_ledger_rows([["Date", "Ticker"], ["2026-01-01", "AAPL"]])

        self.assertEqual(transactions, [])
        self.assertIn("missing required columns", warnings[0])

    def test_parses_holdings_snapshot_with_concentration_and_fx_reporting(self) -> None:
        from investment_agents.domain.portfolio import parse_holding_rows, summarize_holdings

        rows = [
            [
                "Ticker",
                "Shares held",
                "Current price",
                "Purchase value",
                "Current value",
                "$ P/L",
                "Profit status",
                "Currency",
                "Exchange",
            ],
            ["AMD", "10", "160", "1000", "1600", "600", "profit", "USD", "NASDAQ"],
            ["MSFT", "5", "100", "400", "500", "100", "profit", "USD", "NASDAQ"],
            ["BARC", "20", "3", "50", "60", "10", "profit", "GBP", "LON"],
            ["PYPL", "2", "50", "200", "100", "-100", "loss", "USD", "NASDAQ"],
        ]

        holdings, warnings = parse_holding_rows(rows)
        summary = summarize_holdings(
            holdings,
            warnings,
            reporting_currency="USD",
            fx_rates={"GBP": "1.25"},
        )

        self.assertEqual(summary.holding_count, 4)
        self.assertEqual(summary.symbols, ["AMD", "BARC", "MSFT", "PYPL"])
        self.assertEqual(str(summary.total_current_value_by_currency["USD"]), "2200")
        self.assertEqual(str(summary.total_current_value_reporting_currency), "2275.00")
        self.assertEqual(str(summary.total_unrealized_pl_reporting_currency), "612.50")
        alert_types = {alert.alert_type for alert in summary.alerts}
        self.assertEqual(alert_types, {"concentration", "loss_threshold"})
        self.assertIn(
            "AMD is 72.7% of the USD slice, above the 40.0% threshold.",
            summary.concentration_warnings,
        )
        loss_alert = next(alert for alert in summary.alerts if alert.alert_type == "loss_threshold")
        self.assertEqual(loss_alert.symbol, "PYPL")
        self.assertEqual(str(loss_alert.value), "0.5")

    def test_holdings_alert_thresholds_are_configurable(self) -> None:
        from decimal import Decimal

        from investment_agents.domain.portfolio import parse_holding_rows, summarize_holdings

        rows = [
            ["Ticker", "Shares held", "Purchase value", "Current value", "$ P/L", "Currency"],
            ["AMD", "10", "1000", "1600", "600", "USD"],
            ["MSFT", "5", "400", "500", "100", "USD"],
            ["PYPL", "2", "200", "100", "-100", "USD"],
        ]

        holdings, warnings = parse_holding_rows(rows)
        summary = summarize_holdings(
            holdings,
            warnings,
            concentration_alert_threshold=Decimal("0.80"),
            loss_alert_threshold=Decimal("0.60"),
        )

        self.assertEqual(summary.alerts, [])

    def test_holdings_parser_does_not_treat_transaction_rows_as_snapshot(self) -> None:
        from investment_agents.domain.portfolio import parse_holding_rows

        rows = [
            ["Date", "Ticker", "Action", "Shares", "Price", "Fees"],
            ["2026-01-01", "AAPL", "BUY", "10", "100", "1.50"],
        ]

        holdings, warnings = parse_holding_rows(rows)

        self.assertEqual(holdings, [])
        self.assertIn("snapshot value columns", warnings[0])

    def test_ledger_tool_summarizes_mocked_sheet_rows(self) -> None:
        from investment_agents.core.config import Settings
        from investment_agents.storage.market_cache import MarketDataCache
        from investment_agents.tools.google_sheets_ledger import GoogleSheetsLedgerTool

        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = Settings(
                google_ledger_sheet_id="sheet-id",
                google_ledger_range="Ledger!A:Z",
                google_service_account_file="service-account.json",
                reporting_currency="USD",
                storage_db_path=str(Path(tmp_dir) / "market.duckdb"),
            )
            cache = MarketDataCache(settings.storage_db_path)
            cache.store_fx_rate("GBP", "USD", "1.25", source="test")
            tool = GoogleSheetsLedgerTool(settings, cache=cache)
            rows = [
                ["Date", "Symbol", "Side", "Quantity", "Price", "Fees", "Currency"],
                ["2026-01-01", "AAPL", "BUY", "3", "100", "1", "USD"],
                ["2026-01-02", "BARC", "BUY", "2", "150", "2", "GBP"],
            ]

            with patch.object(tool, "fetch_rows", return_value=rows):
                result = tool.summarize_ledger("How is my ledger doing?")

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.data["ledger_summary"]["transaction_count"], 2)
        self.assertEqual(result.data["ledger_summary"]["symbols"], ["AAPL", "BARC"])
        self.assertEqual(
            result.data["ledger_summary"]["net_cash_flow_reporting_currency"],
            "-678.50",
        )

    def test_ledger_tool_summarizes_mocked_holdings_snapshot(self) -> None:
        from investment_agents.core.config import Settings
        from investment_agents.agents.ledger_agent import LedgerInterpretationAgent
        from investment_agents.storage.market_cache import MarketDataCache
        from investment_agents.tools.google_sheets_ledger import GoogleSheetsLedgerTool

        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = Settings(
                google_ledger_sheet_id="sheet-id",
                google_ledger_range="'USD Holdings Portfolio'!A:Z",
                google_service_account_file="service-account.json",
                reporting_currency="USD",
                storage_db_path=str(Path(tmp_dir) / "market.duckdb"),
            )
            cache = MarketDataCache(settings.storage_db_path)
            cache.store_fx_rate("GBP", "USD", "1.25", source="test")
            tool = GoogleSheetsLedgerTool(settings, cache=cache)
            rows = [
                ["Ticker", "Shares held", "Purchase value", "Current value", "$ P/L", "Currency"],
                ["AMD", "10", "1000", "1600", "600", "USD"],
                ["BARC", "20", "50", "60", "10", "GBP"],
            ]

            with patch.object(tool, "fetch_rows", return_value=rows):
                result = tool.summarize_ledger("What is my portfolio exposure?")
                agent_result = LedgerInterpretationAgent(tool).analyze(
                    "What is my portfolio exposure?",
                    "trace-holdings",
                )

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.data["ledger_summary"]["transaction_count"], 0)
        self.assertEqual(result.data["portfolio_summary"]["holding_count"], 2)
        self.assertEqual(
            result.data["portfolio_summary"]["total_current_value_reporting_currency"],
            "1675.00",
        )
        self.assertIn("Portfolio snapshot contains 2 holdings", result.summary)
        self.assertEqual(
            agent_result.metadata["portfolio_summary"]["holding_count"],
            2,
        )

    def test_ledger_tool_summarizes_optional_watchlist_range(self) -> None:
        from investment_agents.agents.ledger_agent import LedgerInterpretationAgent
        from investment_agents.core.config import Settings
        from investment_agents.storage.market_cache import MarketDataCache
        from investment_agents.tools.google_sheets_ledger import GoogleSheetsLedgerTool

        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = Settings(
                google_ledger_sheet_id="sheet-id",
                google_ledger_range="'USD Holdings Portfolio'!A:Z",
                google_watchlist_range="'Sheet10'!A:Z",
                google_service_account_file="service-account.json",
                reporting_currency="USD",
                storage_db_path=str(Path(tmp_dir) / "market.duckdb"),
            )
            tool = GoogleSheetsLedgerTool(settings, cache=MarketDataCache(settings.storage_db_path))
            holdings_rows = [
                ["Ticker", "Shares held", "Purchase value", "Current value", "$ P/L", "Currency"],
                ["AMD", "10", "1000", "1600", "600", "USD"],
            ]
            watchlist_rows = [
                ["Ticker", "Company", "Exchange", "Currency", "Target price", "Status", "Notes"],
                ["NVDA", "Nvidia", "NASDAQ", "USD", "200", "researching", "AI infrastructure"],
                ["SHEL", "Shell", "LON", "GBP", "30", "watching", "Energy exposure"],
            ]

            def mocked_fetch_rows(range_name=None):
                if range_name == settings.google_watchlist_range:
                    return watchlist_rows
                return holdings_rows

            with patch.object(tool, "fetch_rows", side_effect=mocked_fetch_rows):
                result = tool.summarize_ledger("Compare my holdings and watchlist")
                agent_result = LedgerInterpretationAgent(tool).analyze(
                    "Compare my holdings and watchlist",
                    "trace-watchlist",
                )

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.data["portfolio_summary"]["symbols"], ["AMD"])
        self.assertEqual(result.data["watchlist_range"], "'Sheet10'!A:Z")
        self.assertEqual(result.data["watchlist_summary"]["item_count"], 2)
        self.assertEqual(result.data["watchlist_summary"]["symbols"], ["NVDA", "SHEL"])
        self.assertEqual(result.data["watchlist_summary"]["by_status"]["researching"], 1)
        self.assertIn("Watchlist contains 2 items", result.summary)
        self.assertEqual(agent_result.metadata["watchlist_summary"]["symbols"], ["NVDA", "SHEL"])


class WatchlistParsingTests(unittest.TestCase):
    def test_parses_watchlist_rows_with_optional_context(self) -> None:
        from investment_agents.domain.watchlist import parse_watchlist_rows, summarize_watchlist

        rows = [
            ["Ticker", "Company", "Exchange", "Currency", "Target price", "Status", "Notes"],
            ["NVDA", "Nvidia", "NASDAQ", "USD", "200", "researching", "AI infrastructure"],
            ["SHEL", "Shell", "LON", "GBP", "30", "watching", "Energy exposure"],
            ["", "Blank row", "", "", "", "", ""],
        ]

        items, warnings = parse_watchlist_rows(rows)
        summary = summarize_watchlist(items, warnings)

        self.assertEqual(summary.item_count, 2)
        self.assertEqual(summary.symbols, ["NVDA", "SHEL"])
        self.assertEqual(summary.markets, ["LON", "NASDAQ"])
        self.assertEqual(summary.by_status, {"researching": 1, "watching": 1})
        self.assertEqual(str(summary.items[0].target_price), "200")
        self.assertIn("missing symbol", summary.warnings[0])

    def test_watchlist_requires_symbol_column(self) -> None:
        from investment_agents.domain.watchlist import parse_watchlist_rows

        items, warnings = parse_watchlist_rows([["Company"], ["Nvidia"]])

        self.assertEqual(items, [])
        self.assertIn("missing required column: symbol", warnings[0])


class ObservabilityPersistenceTests(unittest.TestCase):
    def test_event_recorder_can_persist_and_reload_jsonl_events(self) -> None:
        from investment_agents.core.observability import EventRecorder

        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "observability" / "events.jsonl"
            first_recorder = EventRecorder(log_path=log_path)
            first_recorder.record(
                event_type="tool_called",
                agent_name="test_agent",
                message="Called a test tool.",
                trace_id="trace-123",
                metadata={"tool_name": "test_tool"},
            )

            second_recorder = EventRecorder(log_path=log_path)
            events = second_recorder.list_events(trace_id="trace-123")

            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event_type"], "tool_called")
            self.assertEqual(events[0]["metadata"]["tool_name"], "test_tool")

    def test_disabled_event_recorder_does_not_store_events(self) -> None:
        from investment_agents.core.observability import EventRecorder

        recorder = EventRecorder(enabled=False)
        recorder.record(
            event_type="tool_called",
            agent_name="test_agent",
            message="This should not be stored.",
            trace_id="trace-disabled",
        )

        self.assertEqual(recorder.list_events(), [])


class StreamlitObservabilityHelperTests(unittest.TestCase):
    def test_event_table_rows_flatten_event_metadata_for_display(self) -> None:
        from investment_agents.ui.observability import event_table_rows, trace_metrics

        events = [
            {
                "timestamp": "2026-08-28T06:00:00+00:00",
                "event_type": "orchestrator_decision",
                "agent_name": "orchestrator_agent",
                "message": "Selected specialist agents.",
                "metadata": {},
            },
            {
                "timestamp": "2026-08-28T06:00:01+00:00",
                "event_type": "tool_called",
                "agent_name": "finnhub_investment_agent",
                "message": "Called quote endpoint.",
                "metadata": {"tool_name": "finnhub_investment_data", "status": "ok"},
            },
        ]

        rows = event_table_rows(events)
        metrics = trace_metrics(events)

        self.assertEqual(rows[0]["agent"], "orchestrator_agent")
        self.assertEqual(rows[1]["tool"], "finnhub_investment_data")
        self.assertEqual(rows[1]["status"], "ok")
        self.assertEqual(metrics, {"events": 2, "agents": 2, "tools": 1})

    def test_portfolio_alert_rows_extract_ledger_alerts_for_display(self) -> None:
        from investment_agents.ui.observability import portfolio_alert_rows

        agent_results = [
            {
                "agent_name": "ledger_interpretation_agent",
                "metadata": {
                    "portfolio_summary": {
                        "alerts": [
                            {
                                "alert_type": "concentration",
                                "severity": "warning",
                                "symbol": "AMD",
                                "currency": "USD",
                                "value": "0.7272727272727272727272727273",
                                "threshold": "0.40",
                                "message": "AMD is 72.7% of the USD slice.",
                            }
                        ]
                    }
                },
            },
            {
                "agent_name": "finnhub_investment_agent",
                "metadata": {"tool_statuses": ["ok"]},
            },
        ]

        rows = portfolio_alert_rows(agent_results)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["type"], "concentration")
        self.assertEqual(rows[0]["symbol"], "AMD")
        self.assertEqual(rows[0]["value"], "72.7%")
        self.assertEqual(rows[0]["threshold"], "40.0%")

    def test_data_source_status_rows_surface_stale_cache_and_skipped_agents(self) -> None:
        from investment_agents.ui.observability import (
            data_source_attention_count,
            data_source_status_rows,
            source_note_rows,
        )

        agent_results = [
            {
                "agent_name": "finnhub_investment_agent",
                "summary": "Using stale cached quote.",
                "tool_calls": [
                    {
                        "tool_name": "finnhub_investment_data",
                        "status": "stale_cache",
                        "summary": "Finnhub is unavailable; using stale cached quote.",
                        "data": {
                            "symbol": "BARC",
                            "provider_symbol": "LON:BARC",
                            "cache_status": "stale",
                            "fetched_at": "2026-01-01T00:00:00+00:00",
                            "stale_fetched_at": "2026-01-01T00:00:00+00:00",
                            "degraded_from": {"status": "rate_limited"},
                        },
                    }
                ],
                "metadata": {"symbols": ["BARC"], "tool_status": "stale_cache"},
            },
            {
                "agent_name": "alphavantage_research_agent",
                "summary": "Alpha Vantage research needs at least one ticker symbol.",
                "tool_calls": [],
                "metadata": {"symbols": [], "tool_status": "needs_symbol"},
            },
        ]

        rows = data_source_status_rows(agent_results)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["agent"], "finnhub_investment_agent")
        self.assertEqual(rows[0]["status"], "stale cache")
        self.assertEqual(rows[0]["cache"], "stale")
        self.assertEqual(rows[0]["provider_symbol"], "LON:BARC")
        self.assertEqual(rows[0]["source_at"], "2026-01-01T00:00:00+00:00")
        self.assertEqual(rows[0]["stale_at"], "2026-01-01T00:00:00+00:00")
        self.assertEqual(rows[0]["degraded_from"], "rate limited")
        self.assertEqual(rows[1]["status"], "needs symbol")
        self.assertEqual(data_source_attention_count(rows), 2)

        source_rows = source_note_rows(
            [
                {
                    "agent_name": "finnhub_investment_agent",
                    "tool_name": "finnhub_investment_data",
                    "symbol": "BARC",
                    "provider_symbol": "LON:BARC",
                    "status": "stale_cache",
                    "cache_status": "stale",
                    "fetched_at": "2026-01-01T00:00:00+00:00",
                    "stale_fetched_at": "2026-01-01T00:00:00+00:00",
                    "degraded_from_status": "rate_limited",
                    "message": "Using stale cached data.",
                }
            ]
        )
        self.assertEqual(source_rows[0]["symbol"], "BARC (LON:BARC)")
        self.assertEqual(source_rows[0]["status"], "stale cache")
        self.assertEqual(source_rows[0]["source_at"], "2026-01-01T00:00:00+00:00")
        self.assertEqual(source_rows[0]["degraded_from"], "rate limited")


class MarketDataCacheTests(unittest.TestCase):
    def test_cache_round_trips_raw_payloads(self) -> None:
        from investment_agents.storage.market_cache import MarketDataCache

        with tempfile.TemporaryDirectory() as tmp_dir:
            cache = MarketDataCache(Path(tmp_dir) / "market.duckdb")
            cache.store_raw_payload("finnhub", "quote", "AAPL", {"c": 101})

            cached = cache.get_fresh_raw_payload("finnhub", "quote", "AAPL", ttl_seconds=3600)

            self.assertIsNotNone(cached)
            self.assertEqual(cached.payload, {"c": 101})
            self.assertTrue(cache.status()["exists"])
            self.assertEqual(cache.status()["raw_payload_count"], 1)
            self.assertEqual(cache.status()["fx_rate_count"], 0)

    def test_cache_returns_latest_fx_rates(self) -> None:
        from investment_agents.storage.market_cache import MarketDataCache

        with tempfile.TemporaryDirectory() as tmp_dir:
            cache = MarketDataCache(Path(tmp_dir) / "market.duckdb")
            cache.store_fx_rate("GBP", "USD", "1.20", source="test", observed_at="2026-01-01T00:00:00+00:00")
            cache.store_fx_rate("GBP", "USD", "1.25", source="test", observed_at="2026-01-02T00:00:00+00:00")
            cache.store_fx_rate("ZAR", "USD", "0.055", source="test")

            rates = cache.latest_fx_rates("USD")

            self.assertEqual(str(rates["GBP"]), "1.25")
            self.assertEqual(str(rates["ZAR"]), "0.055")
            self.assertEqual(str(rates["USD"]), "1")

    def test_finnhub_uses_fresh_cache_without_network_call(self) -> None:
        from investment_agents.core.config import Settings
        from investment_agents.storage.market_cache import MarketDataCache
        from investment_agents.tools.finnhub import FinnhubInvestmentTool

        with tempfile.TemporaryDirectory() as tmp_dir:
            cache = MarketDataCache(Path(tmp_dir) / "market.duckdb")
            stored = cache.store_raw_payload(
                "finnhub_investment_data",
                "quote",
                "AAPL",
                {"c": 101, "o": 100},
            )
            tool = FinnhubInvestmentTool(
                Settings(finnhub_api_key="test-key", storage_db_path=str(cache.db_path)),
                cache=cache,
            )

            with patch("investment_agents.tools.finnhub.requests.get") as mocked_get:
                result = tool.analyze_symbol("AAPL")

            mocked_get.assert_not_called()
            self.assertEqual(result.data["cache_status"], "hit")
            self.assertEqual(result.data["quote"]["c"], 101)
            self.assertEqual(result.data["fetched_at"], stored.fetched_at)

    def test_finnhub_uses_provider_symbol_alias_for_cache_key(self) -> None:
        from investment_agents.core.config import Settings
        from investment_agents.storage.market_cache import MarketDataCache
        from investment_agents.tools.finnhub import FinnhubInvestmentTool

        with tempfile.TemporaryDirectory() as tmp_dir:
            cache = MarketDataCache(Path(tmp_dir) / "market.duckdb")
            stored = cache.store_raw_payload(
                "finnhub_investment_data",
                "quote",
                "LON:BARC",
                {"c": 1.23, "o": 1.20},
            )
            settings = Settings(
                finnhub_api_key="test-key",
                storage_db_path=str(cache.db_path),
                finnhub_symbol_aliases={"BARC": "LON:BARC"},
            )
            tool = FinnhubInvestmentTool(settings, cache=cache)

            with patch("investment_agents.tools.finnhub.requests.get") as mocked_get:
                result = tool.analyze_symbol("BARC")

            mocked_get.assert_not_called()
            self.assertEqual(result.data["symbol"], "BARC")
            self.assertEqual(result.data["provider_symbol"], "LON:BARC")
            self.assertEqual(result.data["cache_status"], "hit")
            self.assertEqual(result.data["fetched_at"], stored.fetched_at)


class ProviderGracefulDegradationTests(unittest.TestCase):
    def test_finnhub_network_failure_returns_tool_result(self) -> None:
        import requests

        from investment_agents.core.config import Settings
        from investment_agents.tools.finnhub import FinnhubInvestmentTool

        tool = FinnhubInvestmentTool(Settings(finnhub_api_key="test-key"))

        with patch("investment_agents.tools.finnhub.requests.get") as mocked_get:
            mocked_get.side_effect = requests.Timeout("timed out")
            result = tool.analyze_symbol("AAPL")

        self.assertEqual(result.status, "provider_error")
        self.assertEqual(result.data["symbol"], "AAPL")
        self.assertEqual(result.data["provider_symbol"], "AAPL")
        self.assertEqual(result.data["error_type"], "Timeout")

    def test_finnhub_http_429_returns_rate_limited_tool_result(self) -> None:
        import requests

        from investment_agents.core.config import Settings
        from investment_agents.tools.finnhub import FinnhubInvestmentTool

        response = requests.Response()
        response.status_code = 429
        error = requests.HTTPError(response=response)
        tool = FinnhubInvestmentTool(Settings(finnhub_api_key="test-key"))

        with patch("investment_agents.tools.finnhub.requests.get") as mocked_get:
            mocked_get.return_value.raise_for_status.side_effect = error
            result = tool.analyze_symbol("AAPL")

        self.assertEqual(result.status, "rate_limited")
        self.assertEqual(result.data["http_status"], 429)

    def test_finnhub_provider_failure_uses_latest_stale_cache(self) -> None:
        import requests

        from investment_agents.core.config import Settings
        from investment_agents.storage.market_cache import MarketDataCache
        from investment_agents.tools.finnhub import FinnhubInvestmentTool

        with tempfile.TemporaryDirectory() as tmp_dir:
            cache = MarketDataCache(Path(tmp_dir) / "market.duckdb")
            cache.store_raw_payload(
                "finnhub_investment_data",
                "quote",
                "AAPL",
                {"c": 99, "o": 98},
                fetched_at="2026-01-01T00:00:00+00:00",
            )
            tool = FinnhubInvestmentTool(
                Settings(
                    finnhub_api_key="test-key",
                    market_cache_ttl_seconds=0,
                    storage_db_path=str(cache.db_path),
                ),
                cache=cache,
            )

            with patch("investment_agents.tools.finnhub.requests.get") as mocked_get:
                mocked_get.side_effect = requests.Timeout("timed out")
                result = tool.analyze_symbol("AAPL")

        self.assertEqual(result.status, "stale_cache")
        self.assertEqual(result.data["cache_status"], "stale")
        self.assertEqual(result.data["quote"], {"c": 99, "o": 98})
        self.assertEqual(result.data["degraded_from"]["status"], "provider_error")
        self.assertEqual(result.data["fetched_at"], "2026-01-01T00:00:00+00:00")
        self.assertEqual(result.data["stale_fetched_at"], "2026-01-01T00:00:00+00:00")

    def test_alphavantage_rate_limit_payload_returns_tool_result_without_caching(self) -> None:
        from investment_agents.core.config import Settings
        from investment_agents.storage.market_cache import MarketDataCache
        from investment_agents.tools.alphavantage import AlphaVantageResearchTool

        with tempfile.TemporaryDirectory() as tmp_dir:
            cache = MarketDataCache(Path(tmp_dir) / "market.duckdb")
            tool = AlphaVantageResearchTool(
                Settings(alphavantage_api_key="test-key", storage_db_path=str(cache.db_path)),
                cache=cache,
            )

            with patch("investment_agents.tools.alphavantage.requests.get") as mocked_get:
                mocked_get.return_value.raise_for_status.return_value = None
                mocked_get.return_value.json.return_value = {
                    "Note": "Thank you for using Alpha Vantage. Our standard API rate limit is reached."
                }
                result = tool.research_symbol("MSFT")

            self.assertEqual(result.status, "rate_limited")
            self.assertEqual(result.data["symbol"], "MSFT")
            self.assertIn("rate limit", result.data["provider_message"].lower())
            self.assertEqual(cache.status()["raw_payload_count"], 0)

    def test_alphavantage_rate_limit_payload_uses_latest_stale_cache(self) -> None:
        from investment_agents.core.config import Settings
        from investment_agents.storage.market_cache import MarketDataCache
        from investment_agents.tools.alphavantage import AlphaVantageResearchTool

        with tempfile.TemporaryDirectory() as tmp_dir:
            cache = MarketDataCache(Path(tmp_dir) / "market.duckdb")
            cache.store_raw_payload(
                "alphavantage_research",
                "news_sentiment",
                "MSFT",
                {"feed": [{"title": "Cached Microsoft headline"}]},
                fetched_at="2026-01-01T00:00:00+00:00",
            )
            tool = AlphaVantageResearchTool(
                Settings(
                    alphavantage_api_key="test-key",
                    market_cache_ttl_seconds=0,
                    storage_db_path=str(cache.db_path),
                ),
                cache=cache,
            )

            with patch("investment_agents.tools.alphavantage.requests.get") as mocked_get:
                mocked_get.return_value.raise_for_status.return_value = None
                mocked_get.return_value.json.return_value = {
                    "Note": "Thank you for using Alpha Vantage. Our standard API rate limit is reached."
                }
                result = tool.research_symbol("MSFT")

        self.assertEqual(result.status, "stale_cache")
        self.assertEqual(result.data["cache_status"], "stale")
        self.assertEqual(result.data["headlines"], ["Cached Microsoft headline"])
        self.assertEqual(result.data["degraded_from"]["status"], "rate_limited")
        self.assertEqual(result.data["fetched_at"], "2026-01-01T00:00:00+00:00")
        self.assertEqual(result.data["stale_fetched_at"], "2026-01-01T00:00:00+00:00")

    def test_alphavantage_malformed_feed_returns_tool_result(self) -> None:
        from investment_agents.core.config import Settings
        from investment_agents.tools.alphavantage import AlphaVantageResearchTool

        tool = AlphaVantageResearchTool(Settings(alphavantage_api_key="test-key"))

        with patch("investment_agents.tools.alphavantage.requests.get") as mocked_get:
            mocked_get.return_value.raise_for_status.return_value = None
            mocked_get.return_value.json.return_value = {"feed": "not-a-list"}
            result = tool.research_symbol("MSFT")

        self.assertEqual(result.status, "malformed_response")
        self.assertEqual(result.data["error_type"], "ValueError")


class SpecialistSymbolSelectionTests(unittest.TestCase):
    def test_finnhub_agent_uses_hinted_symbols_with_configured_cap(self) -> None:
        from investment_agents.agents.finnhub_agent import FinnhubInvestmentAgent
        from investment_agents.core.config import Settings
        from investment_agents.tools.finnhub import FinnhubInvestmentTool

        settings = Settings(finnhub_api_key="", max_enrichment_symbols=2)
        agent = FinnhubInvestmentAgent(FinnhubInvestmentTool(settings), settings=settings)

        result = agent.analyze(
            "Check my holdings",
            "trace-symbol-cap",
            symbols=["AMD", "MSFT", "NVDA"],
        )

        self.assertEqual(result.metadata["symbols"], ["AMD", "MSFT"])
        self.assertEqual(result.metadata["tool_statuses"], ["needs_configuration", "needs_configuration"])

    def test_alphavantage_agent_degrades_without_explicit_or_hinted_symbols(self) -> None:
        from investment_agents.agents.alphavantage_agent import AlphaVantageResearchAgent
        from investment_agents.core.config import Settings
        from investment_agents.tools.alphavantage import AlphaVantageResearchTool

        settings = Settings(alphavantage_api_key="")
        agent = AlphaVantageResearchAgent(AlphaVantageResearchTool(settings), settings=settings)

        result = agent.analyze("Research market events", "trace-needs-symbol")

        self.assertEqual(result.metadata["symbols"], [])
        self.assertEqual(result.metadata["tool_status"], "needs_symbol")
        self.assertIn("needs at least one ticker", result.summary)

    def test_alphavantage_tool_uses_provider_symbol_alias_for_request(self) -> None:
        from investment_agents.core.config import Settings
        from investment_agents.tools.alphavantage import AlphaVantageResearchTool

        settings = Settings(
            alphavantage_api_key="test-key",
            alphavantage_symbol_aliases={"BARC": "BARC.LON"},
        )
        tool = AlphaVantageResearchTool(settings)

        with patch("investment_agents.tools.alphavantage.requests.get") as mocked_get:
            mocked_get.return_value.json.return_value = {
                "feed": [{"title": "Barclays headline"}],
            }
            mocked_get.return_value.raise_for_status.return_value = None
            result = tool.research_symbol("BARC")

        params = mocked_get.call_args.kwargs["params"]
        self.assertEqual(params["tickers"], "BARC.LON")
        self.assertEqual(result.data["symbol"], "BARC")
        self.assertEqual(result.data["provider_symbol"], "BARC.LON")
        self.assertEqual(result.data["headlines"], ["Barclays headline"])
        self.assertTrue(result.data["fetched_at"])


class ApiContractTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["FINNHUB_API_KEY"] = ""
        os.environ["ALPHAVANTAGE_API_KEY"] = ""
        os.environ["GOOGLE_LEDGER_SHEET_ID"] = ""

    def test_api_exposes_agents_chat_and_observability(self) -> None:
        from fastapi.testclient import TestClient
        from investment_agents.tools.base import ToolResult
        from investment_agents.tools.web_search import WebSearchTool

        import agent_api

        client = TestClient(agent_api.app)

        health = client.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")

        agents = client.get("/agents")
        self.assertEqual(agents.status_code, 200)
        self.assertEqual(len(agents.json()), 4)

        readiness = client.get("/tools/readiness")
        self.assertEqual(readiness.status_code, 200)
        self.assertEqual(len(readiness.json()), 4)

        observability_status = client.get("/observability/status")
        self.assertEqual(observability_status.status_code, 200)
        self.assertIn("enabled", observability_status.json())

        storage_status = client.get("/storage/status")
        self.assertEqual(storage_status.status_code, 200)
        self.assertIn("db_path", storage_status.json())

        with patch.object(
            WebSearchTool,
            "search",
            return_value=ToolResult(
                tool_name="web_search",
                summary="No web references in this test.",
                data={"citations": []},
            ),
        ):
            chat = client.post(
                "/chat",
                json={"message": "Review my portfolio loss and AAPL news sentiment"},
            )
        self.assertEqual(chat.status_code, 200)
        payload = chat.json()
        self.assertEqual(payload["routing_decision"]["symbols"], ["AAPL"])
        self.assertEqual(
            payload["selected_agents"],
            [
                "ledger_interpretation_agent",
                "finnhub_investment_agent",
                "alphavantage_research_agent",
                "web_search_agent",
            ],
        )
        self.assertIn("source_notes", payload)
        self.assertIn("citations", payload)
        self.assertTrue(payload["source_notes"])
        self.assertIn(
            "needs_configuration",
            {note["status"] for note in payload["source_notes"]},
        )

        events = client.get("/observability/events", params={"trace_id": payload["trace_id"]})
        self.assertEqual(events.status_code, 200)
        self.assertGreaterEqual(len(events.json()["events"]), 1)


if __name__ == "__main__":
    unittest.main()
