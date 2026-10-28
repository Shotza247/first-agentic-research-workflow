# Setup and Integrations

Run commands from the repository root. Reuse `.venv` if it already exists.

## Install

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Dependencies include the local Transformers/PyTorch stack. The first local model
run downloads model weights. `.env.example` is a template, not a loaded file.
Do not commit keys or service-account credentials.

## Google Sheets Ledger

The existing adapter reads a spreadsheet directly with read-only Sheets API access.
Enable the Sheets API for your Google Cloud project, obtain a service-account JSON
credential file, and share the spreadsheet with that account's email as Viewer.

```dotenv
GOOGLE_LEDGER_SHEET_ID=spreadsheet_id_from_the_url
GOOGLE_SERVICE_ACCOUNT_FILE=C:/path/to/service-account.json
GOOGLE_LEDGER_RANGE="'Holdings'!A:Z"
GOOGLE_WATCHLIST_RANGE=
```

The ID is between `/d/` and `/edit` in the spreadsheet URL. Configure an A1 range
whose first row contains headers. The tool supports one primary range and an
optional watchlist range in the same spreadsheet.

| Sheet shape | Expected columns |
| --- | --- |
| Transactions | `symbol`, `side`, `quantity`; optional `date`, `price`, `fees`, `amount`, `currency` |
| Holdings snapshot | `symbol`, `quantity`, plus a snapshot field such as `current value`, `purchase value`, `p/l`, or `profit status` |
| Watchlist | `symbol`; optional `name`, `currency`, `market`, `target price`, `current price`, `status`, `reason` |

Common aliases such as `ticker`, `shares`, and `cost basis` are supported; exact
parsing rules live in `src/investment_agents/domain/`. Headers and number formats
must be checked against your actual sheet. Set `GOOGLE_WATCHLIST_RANGE` only when
using a separate watchlist tab. Ask `Summarize my portfolio holdings` after restart
to verify access and parsing. Readiness checks settings presence, not successful
authentication. Sheet read errors can fail the request; market-provider fallbacks
do not apply to the Sheets adapter.

## Market and Research Sources

- `FINNHUB_API_KEY`: ticker quotes and base-currency exchange rates.
- `ALPHAVANTAGE_API_KEY`: ticker news sentiment and macroeconomic headlines.
- Web research uses DuckDuckGo search and requires no API key.
- `FINNHUB_SYMBOL_ALIASES` and `ALPHAVANTAGE_SYMBOL_ALIASES`: optional comma-separated
  `symbol=provider_symbol` mappings; verify symbols with each provider.
- `MAX_ENRICHMENT_SYMBOLS`: maximum symbols handled by each market/research wrapper,
  default 3. Explicit question tickers take precedence over ledger-derived symbols.

Market and macro questions route to web search plus the relevant provider agents.
Currency codes such as `USD` use Finnhub's FX rates and Alpha Vantage's macro-news
feed instead of being mistaken for stock tickers. Replies contain numbered
references, and `POST /chat` also returns a `citations` list with each source's
URL, claim, publication time (when supplied), and retrieval time.

Web results are fetched per request and are not cached. Finnhub/Alpha Vantage
responses use the configured DuckDB cache. Provider keys remain optional: if a
provider is not configured, its unavailable status is shown while the other
sources can still contribute. Yahoo Finance, Google Finance, Drive document
ingestion, and MongoDB retrieval are not implemented adapters. Sheets access does
not imply general Drive document access.

## Storage and Reporting

- `STORAGE_DB_PATH`: DuckDB file, default `data/investment_agents.duckdb`.
- `MARKET_CACHE_TTL_SECONDS`: quote/news freshness window, default 900.
- `PROVIDER_REQUEST_TIMEOUT_SECONDS`: maximum read wait for each uncached provider
  request, default 10. The client also uses a 3.05-second connection timeout.
  These constrain connection and idle reads, but cannot impose a strict total
  wall-clock limit on every DNS or provider-side failure mode.
- `REPORTING_CURRENCY`: default USD.
- `STATIC_FX_RATES`: manual rates into the reporting currency, for example
  `GBP=1.25,ZAR=0.055`. These are illustrative values, not live exchange rates.
- `CONCENTRATION_ALERT_THRESHOLD` and `LOSS_ALERT_THRESHOLD`: decimal ratios,
  defaults 0.40 and 0.10. Calculations depend on supplied sheet values.
- `OBSERVABILITY_LOG_PATH`: optional JSONL event persistence; otherwise events
  remain in memory. `OBSERVABILITY_MAX_EVENTS` defaults to 500.

Missing FX rates are reported rather than used to fabricate combined totals.
Market/research tools use fresh cached payloads, then live requests, then stale
cached payloads on provider failure where available. Returned metadata identifies
degraded results and timestamps.

## Model and UI Settings

Local chat uses Transformers and optional `HF_TOKEN` authentication for restricted
models. The API's `model_id` metadata does not prove a model was invoked.
`LLM_PROVIDER`, `OPENAI_API_KEY`, `OPENAI_MODEL`, and `LLM_MAX_OUTPUT_TOKENS` are
reserved settings: current API response generation does not use them.

The API/default CLI load `.env` via shared settings. Set Streamlit's
`AGENT_API_URL` in its process environment or sidebar as shown in the
[README](../README.md). Restart processes after configuration changes.

## Docker

```powershell
docker compose --progress plain build
docker compose up
```

A complete build remains unverified following the reported build failure. Compose
publishes API port 8000 and Streamlit port 8501. Its UI connects to `http://api:8000`.
Do not reuse occupied host ports. The configuration has an `agent-data` volume but
no service-account credential mount: mount that file explicitly and use its Linux
container path before attempting Sheets access from Docker. Keep credential files
outside the build context; `.env` is excluded by `.dockerignore`.
