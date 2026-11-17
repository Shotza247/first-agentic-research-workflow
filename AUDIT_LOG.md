# Audit Log — First Agent project

This file preserves dated investigation history. Earlier entries describe the code
at that time and may no longer describe current behavior. For current architecture
and setup, use [README.md](README.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## 2026-11-17 - Launcher Structure Cleanup

- Grouped the CLI, FastAPI, and Streamlit launcher scripts under `scripts/`.
- Updated local and Docker launch commands, Streamlit tests, and architecture/setup
  documentation to match the new layout.
- Application implementation remains in `src/investment_agents/`.

## 2026-09-16 - Documentation Consolidation

- Release verification: `.venv\Scripts\python.exe -m unittest discover -s tests -v`
  passed all 42 tests in 107.748 seconds during lifecycle commit preparation.
  This does not verify real-model synthesis, live provider credentials, or Docker.
- Changes grouped into backend, UI/tests, Docker configuration, and documentation
  commits. Local `.env` and unrelated VS Code changes were excluded.

- Removed redundant prototype reference documents and the separate future blueprint.
- Consolidated current integration setup in `docs/SETUP.md` and current runtime
  responsibilities in `docs/ARCHITECTURE.md`.
- Retained this dated audit history; it is not a current architecture specification.
- Scope: documentation only. No runtime modules or credentials changed.

## 2026-09-27 - Initial Live Market Query Delay

- Status: partially fixed; service restart and browser verification remain required.
- Symptom: Streamlit appeared blank while processing a ticker research request.
- Scope: Streamlit `/chat` request and live Finnhub/Alpha Vantage tools.
- Evidence:
  - `.env` has Finnhub and Alpha Vantage keys set; `/tools/readiness` reports both ready.
  - `Research AAPL news sentiment` reached the API. Its trace recorded a Finnhub quote
    after roughly 62 seconds and Alpha Vantage news roughly two seconds later.
  - A repeat request completed in about four seconds using cached provider payloads.
- Changes:
  - Added `PROVIDER_REQUEST_TIMEOUT_SECONDS` with a default 10-second read limit and
    a 3.05-second provider connection timeout.
  - Added Streamlit fallback handling for unexpected response-rendering errors.
- Verification:
  - API health and tool readiness returned HTTP 200 before the source changes.
  - Repeat AAPL `/chat` request completed successfully from cache.
  - Full regression run was interrupted after no further output; it did not finish,
    so no new full-suite pass is claimed.
- Follow-up:
  - Restart API and Streamlit, verify the first uncached ticker request, and inspect
    its trace. If provider calls still exceed the expected window, capture API logs.

Format (each entry):
- ID: unique short id
- Date: ISO 8601 timestamp (local)
- Severity: Critical / High / Medium / Low
- Affected files: list of files (path relative to repo root)
- Description: short description of the problem or observation
- Action taken: what was changed, with links to files where applicable
- Status: Open / Fixed / Mitigated / Won't fix
- Notes / Next steps: recommendations or follow-ups

---

## Entries

### ID: issue-001
- Date: 2026-08-23T19:38:20+02:00
- Severity: Medium
- Affected files:
  - first_agent.py
- Description: No Streamlit frontend existed; user requested a web UI to interact with the agent.
- Action taken: Added `streamlit_frontend.py` which loads the same model and exposes a text-area UI and chat history. Caches the transformers pipeline with @st.cache_resource to avoid reloading the model on each interaction.
  - File added: `streamlit_frontend.py`
- Status: Fixed
- Notes / Next steps: Consider adding streaming generation or token-by-token updates; optionally add authentication or usage limits if exposing on a shared host.

---

### ID: issue-002
- Date: 2026-08-23T19:55:52+02:00
- Severity: Low
- Affected files:
  - README.md
- Description: README lacked usage instructions for the new Streamlit frontend and general startup guidance was minimal.
- Action taken: Updated `README.md` to include setup, CLI usage, Streamlit usage and notes about HF_TOKEN and model choices.
- Status: Fixed
- Notes / Next steps: Keep README in sync if code moves or model changes.

---

### ID: issue-003
- Date: 2026-08-23T19:57:54+02:00
- Severity: Low
- Affected files:
  - requirements.txt
- Description: `streamlit` was not listed as a dependency, so installing requirements did not install Streamlit for the new frontend.
- Action taken: Appended `streamlit` to `requirements.txt`.
- Status: Fixed
- Notes / Next steps: Consider adding a developer extras file (requirements-dev.txt) for local tooling.

---

### ID: issue-004
- Date: 2026-08-24T07:13:18+02:00
- Severity: High
- Affected files:
  - first_agent.py
  - streamlit_frontend.py
- Description: The code assumed a specific transformers pipeline output shape (response[0]["generated_text"] being a list representing chat history). Some `transformers` versions or models return a string or different structure, causing parsing errors and confusing output (e.g. "#attachment:Pasted text #1" or other malformed responses).
- Action taken:
  - Rewrote the response-parsing logic in both `first_agent.py` and `streamlit_frontend.py` to:
    - Inspect the returned object safely (handle list/dict/string forms)
    - Support `generated_text` as either a list (chat history) or a string reply
    - Provide fallbacks and robust stringification when the structure is unexpected
  - Added timing (time.perf_counter) around model calls and displayed response times in seconds in both CLI and Streamlit UI.
- Status: Fixed / Mitigated
- Notes / Next steps:
  - If a model still returns an unexpected structure, capture and paste a raw example of the Python object so the parser can be extended.
  - Consider adding unit tests that simulate common pipeline outputs to prevent regressions.

---

### ID: issue-005
- Date: 2026-08-24T07:37:08+02:00
- Severity: High
- Affected files:
  - requirements.txt
  - README.md
- Description: Users encountered `ModuleNotFoundError: No module named 'torchvision'` at runtime. Some models or pipelines import torchvision indirectly.
- Action taken:
  - Added `torchvision` to `requirements.txt`.
  - Updated README to recommend installing both `torch` and `torchvision` from the PyTorch CPU wheel index for CPU-only machines and added troubleshooting commands for pip and conda.
- Status: Fixed / Mitigated
- Notes / Next steps: Keep torch/torchvision compatibility in mind — wheels must match the installed torch version. Consider pinning to compatible versions or using the official install instructions per environment.

---

### ID: issue-006
- Date: 2026-08-24T07:40:19+02:00
- Severity: Medium
- Affected files:
  - requirements.txt
  - first_agent.py
  - streamlit_frontend.py
- Description: Risk of torch/torchvision version mismatches which can lead to runtime ImportErrors or ABI incompatibilities.
- Action taken:
  - Pinned `torch==2.2.0` and `torchvision==0.17.0` in `requirements.txt` with a comment explaining these are CPU-friendly pins and should be changed for CUDA builds.
  - Added startup checks to both Python entrypoints (`first_agent.py`, `streamlit_frontend.py`) that attempt to `import torchvision` and provide a clear, actionable message if it's missing. The CLI script exits with a friendly message; the Streamlit app displays a warning and stops.
- Status: Fixed / Mitigated
- Notes / Next steps:
  - Optionally implement a runtime check that compares `torch.__version__` with `torchvision.__version__` and prints a specific mismatch message (recommended).
  - Optionally relax exact pins to ranges (e.g., `torch~=2.2`) depending on your compatibility policy.

---

## How to use this audit log as a code-review skill
1. When a new issue is found during review or testing, add a new entry below using the template above. Keep entries concise and factual.
2. Include affected file paths and any commands needed to reproduce the issue.
3. Mark status as `Open` if the problem still needs work, or `Fixed` once a PR has been merged and validated.
4. For high-severity findings, create a `todos` entry in the session DB or open a GitHub issue and reference it here.

## Suggested improvements (future)
- Add a small script (or CLI command) to append audit entries automatically from the terminal or CI.
- Integrate with the repo's issue tracker: create GitHub issues for `High`/`Critical` entries and store the issue number in this log.
- Add automated runtime compatibility checks to CI (verify torch/torchvision version, basic import smoke tests for transformers, streamlit, etc.).

---

_Last update: 2026-08-24T08:01:22+02:00_

---

### ID: issue-007
- Date: 2026-08-25T20:54:35+02:00
- Severity: Medium
- Affected files:
  - streamlit_frontend.py
- Description: Streamlit raised StreamlitAPIException: "st.session_state.user_input cannot be modified after the widget with key 'user_input' is instantiated." This occurred because the code attempted to assign to st.session_state.user_input after creating the text_area widget.
- Action taken:
  - Refactored the Streamlit UI so the Send button uses an on_click callback (handle_send) which performs the model call, updates chat state, records response time, and clears the input. Mutating widget-bound session_state keys inside a button callback avoids the StreamlitAPIException.
  - Display the measured response time (seconds) alongside the assistant reply using st.session_state.last_elapsed.
- Status: Fixed
- Notes / Next steps:
  - If a nicer UX is desired (live spinner or progress), consider moving to a form submit or an async background worker with progress updates; current approach shows elapsed time after completion.
  - Add a unit test or CI smoke test that verifies the Streamlit script runs and that session_state mutations do not raise exceptions.

_Last update: 2026-08-25T20:54:35+02:00_

---

### ID: issue-008
- Date: 2026-08-26T16:19:00+02:00
- Severity: Medium
- Affected files:
  - streamlit_frontend.py
- Description: The Streamlit UI had a duplicate chat rendering section and a response timer display that was cluttering the chat and creating repeated output blocks. This was a styling/UX issue caused by repeated rendering blocks inserted during earlier fixes.
- Action taken:
  - Removed the duplicate "Show the chat history" block in `streamlit_frontend.py`.
  - Removed the timer logic from the assistant reply rendering so responses display cleanly without timing metadata.
  - Kept the callback-based send flow and input clearing to avoid Streamlit session-state API errors.
- Status: Fixed
- Notes / Next steps:
  - Keep the UI simple and avoid duplicated render sections; if timing is needed again, add it in a single place only.
  - Consider a small UI smoke test to catch duplicate block regressions.

_Last update: 2026-08-26T16:19:00+02:00_

---

### ID: issue-009
- Date: 2026-08-27T23:19:25+02:00
- Severity: Medium
- Affected files:
  - first_agent.py
  - streamlit_frontend.py
  - README.md
- Description: `streamlit_frontend.py` duplicated the model-loading, chat, and response-parsing behavior from `first_agent.py` instead of using it. `first_agent.py` also behaved like a CLI script rather than an import-safe reusable service layer, which would make future FastAPI, React, or RAG integrations awkward.
- Action taken:
  - Refactored `first_agent.py` into a reusable service layer with `FirstAgent`, `AgentResponse`, `initial_chat()`, lazy model loading, shared response parsing, and a guarded CLI entrypoint.
  - Updated `streamlit_frontend.py` to call the shared `FirstAgent` service instead of creating its own transformers pipeline.
  - Updated `README.md` to document service-layer reuse from other applications.
- Status: Fixed
- Notes / Next steps:
  - Add focused tests for `parse_pipeline_response()` using mocked transformers outputs.
  - When adding FastAPI, call `FirstAgent` from an API wrapper rather than putting HTTP concerns inside `first_agent.py`.

_Last update: 2026-08-27T23:19:25+02:00_

---

### ID: issue-010
- Date: 2026-08-27T23:53:56+02:00
- Severity: Medium
- Affected files:
  - agent_api.py
  - streamlit_frontend.py
  - requirements.txt
  - README.md
- Description: The project needed an HTTP boundary so the reusable `FirstAgent` service could be consumed by Streamlit now and by future JavaScript/React applications later.
- Action taken:
  - Added `agent_api.py`, a FastAPI app with `GET /health` and stateless `POST /chat` endpoints around `FirstAgent`.
  - Updated `streamlit_frontend.py` to use Streamlit chat elements and call the FastAPI `/chat` endpoint over HTTP.
  - Added FastAPI, uvicorn, and requests dependencies.
  - Updated `README.md` with API and Streamlit startup instructions.
- Status: Fixed
- Notes / Next steps:
  - Add a React client against the same `/chat` contract when ready.
  - Consider streaming responses later with Server-Sent Events or WebSockets.
  - Add automated API tests with a mocked `FirstAgent` to avoid loading the local model in CI.

_Last update: 2026-08-27T23:53:56+02:00_

---

### ID: issue-011
- Date: 2026-08-28T00:54:45+02:00
- Severity: Low
- Affected files:
  - agent_api.py
  - streamlit_frontend.py
- Description: Running `uvicorn` manually produced `[WinError 10013] An attempt was made to access a socket in a way forbidden by its access permissions`.
- Action taken:
  - Checked Windows TCP port exclusions; port `8000` was not reserved.
  - Verified `GET http://127.0.0.1:8000/health` returned `{"status":"ok","model_id":"HuggingFaceTB/SmolLM2-360M-Instruct"}`.
  - Confirmed with `netstat -ano | findstr :8000` that `127.0.0.1:8000` was already listening under PID `88080`.
- Status: Monitoring
- Notes / Next steps:
  - If starting a fresh API server, stop the existing process first or use a different port such as `8001`.
  - If using a different API port, update Streamlit's sidebar API URL or set `AGENT_API_URL`.

_Last update: 2026-08-28T00:54:45+02:00_

---

### ID: issue-012
- Date: 2026-08-28T01:46:04+02:00
- Severity: Medium
- Affected files:
  - src/investment_agents/
  - first_agent.py
  - agent_api.py
  - streamlit_frontend.py
  - Dockerfile
  - docker-compose.yml
  - .dockerignore
  - .env.example
  - docs/ARCHITECTURE.md
  - README.md
- Description: The repository structure was still centered on a single agent script and two root-level frontends, which would make the planned orchestrator + three specialist trading analysis agents difficult to extend, observe, and host in Docker.
- Action taken:
  - Introduced a `src/investment_agents/` package with `core`, `tools`, `agents`, `api`, and `ui` layers.
  - Added specialist agent skeletons for Google Sheets ledger interpretation, Finnhub investment analysis, and Alpha Vantage research analysis.
  - Added an `OrchestratorAgent` that routes user requests to relevant specialist agents and returns trace IDs, selected agents, and agent results.
  - Added an in-memory observability foundation for routing decisions, agent starts, and tool calls.
  - Kept root compatibility launchers for `first_agent.py`, `agent_api.py`, and `streamlit_frontend.py`.
  - Added Docker and docker-compose scaffolding for API and Streamlit services.
  - Rewrote README and added `docs/ARCHITECTURE.md`.
- Status: Fixed / Foundation
- Notes / Next steps:
  - Implement live Google Sheets worksheet/range extraction.
  - Expand Finnhub and Alpha Vantage tools beyond the first quote/news endpoints.
  - Decide whether observability should use OpenTelemetry, LangSmith, Phoenix, or a persistent event store.
  - Add automated tests around orchestrator routing and API contract.

_Last update: 2026-08-28T01:46:04+02:00_

---

### ID: issue-013
- Date: 2026-08-28T02:06:11+02:00
- Severity: Medium
- Affected files:
  - src/investment_agents/core/__init__.py
  - src/investment_agents/core/messages.py
  - src/investment_agents/agents/orchestrator.py
  - src/investment_agents/agents/finnhub_agent.py
  - src/investment_agents/agents/alphavantage_agent.py
- Description: Live API verification exposed two architecture issues: importing the API path could still import the heavy local LLM/transformers wrapper through `core/__init__.py`, and ticker extraction uppercased the whole question, causing words like "my" to be treated as symbol `MY`.
- Action taken:
  - Added `core/messages.py` for lightweight chat types/defaults.
  - Made `core/__init__.py` export only lightweight chat constants/types to keep API startup model-free.
  - Updated orchestrator routing to treat explicit uppercase ticker symbols as a signal for Finnhub and Alpha Vantage analysis.
  - Updated Finnhub and Alpha Vantage symbol extraction to inspect the original text so lowercase words are not mistaken for tickers.
- Status: Fixed
- Notes / Next steps:
  - Replace the simple regex ticker parser with a proper symbol resolver/watchlist service once portfolio/watchlist data exists.
  - Keep heavyweight model imports out of API startup paths unless the API endpoint explicitly needs local generation.

_Last update: 2026-08-28T02:06:11+02:00_

---

### ID: issue-014
- Date: 2026-08-28T02:17:11+02:00
- Severity: Medium
- Affected files:
  - src/investment_agents/domain/
  - src/investment_agents/agents/routing.py
  - src/investment_agents/agents/orchestrator.py
  - src/investment_agents/api/
  - tests/test_multi_agent_architecture.py
  - docs/ARCHITECTURE.md
  - README.md
- Description: Orchestrator routing and ticker extraction needed a stronger shared domain boundary and automated tests so the multi-agent architecture can evolve safely.
- Action taken:
  - Added `domain/` with `RouteDecision`, `AnalysisFocus`, and `extract_ticker_symbols()`.
  - Added `AgentRouter` to isolate routing policy from orchestration execution.
  - Updated the orchestrator and API response contract to include `routing_decision`.
  - Updated Finnhub and Alpha Vantage agents to use shared ticker extraction.
  - Added `tests/test_multi_agent_architecture.py` covering ticker extraction, orchestrator routing, observability events, and FastAPI endpoints.
  - Updated README and architecture docs with the routing contract and test command.
- Status: Fixed / Foundation
- Notes / Next steps:
  - Replace deterministic routing with an LLM classifier or policy engine once tool outputs and user examples are richer.
  - Add fixture-backed tests for live tool payload normalization when Google Sheets, Finnhub, and Alpha Vantage integrations deepen.

_Last update: 2026-08-28T02:17:11+02:00_

---

### ID: issue-015
- Date: 2026-08-28T02:29:11+02:00
- Severity: Medium
- Affected files:
  - src/investment_agents/core/config.py
  - src/investment_agents/tools/
  - src/investment_agents/agents/orchestrator.py
  - src/investment_agents/api/
  - src/investment_agents/ui/streamlit_app.py
  - tests/test_multi_agent_architecture.py
  - docs/ARCHITECTURE.md
  - README.md
- Description: The platform needed a central tool wiring/readiness layer so Docker/runtime configuration could be inspected safely and the orchestrator did not directly construct external integrations.
- Action taken:
  - Fixed `Settings` so environment variables are read at instantiation time instead of module import time.
  - Added blank-string-to-None handling for credential environment variables.
  - Added `ToolReadiness` and `ToolRegistry`.
  - Added readiness methods to the Google Sheets ledger, Finnhub, and Alpha Vantage tools.
  - Updated `OrchestratorAgent` to construct specialists from `ToolRegistry`.
  - Added `GET /tools/readiness` and surfaced it in the Streamlit sidebar.
  - Expanded tests to cover runtime config and secret-safe readiness reporting.
- Status: Fixed / Foundation
- Notes / Next steps:
  - Add health checks that distinguish API readiness from optional tool readiness.
  - Add fixture-backed tool normalization tests as live integrations become richer.

_Last update: 2026-08-28T02:29:11+02:00_

---

### ID: issue-016
- Date: 2026-08-28T03:02:45+02:00
- Severity: Medium
- Affected files:
  - src/investment_agents/core/config.py
  - src/investment_agents/core/observability.py
  - src/investment_agents/api/
  - docker-compose.yml
  - .env.example
  - .gitignore
  - docs/ARCHITECTURE.md
  - README.md
  - tests/test_multi_agent_architecture.py
- Description: Observability was memory-only, so orchestrator decisions, specialist agent starts, and tool calls would be lost on process/container restart.
- Action taken:
  - Added configurable JSONL persistence to `EventRecorder`.
  - Added `OBSERVABILITY_LOG_PATH` and `OBSERVABILITY_MAX_EVENTS` settings.
  - Added `GET /observability/status` for safe runtime observability status.
  - Updated Docker Compose to persist `/app/data` with an `agent-data` volume and default trace log path `/app/data/observability/events.jsonl`.
  - Updated docs and `.env.example` for persisted observability.
  - Added tests for event persistence, disabled recording, and observability status API behavior.
- Status: Fixed / Foundation
- Notes / Next steps:
  - Add a richer trace viewer in Streamlit or a dedicated dashboard.
  - Consider OpenTelemetry or a database-backed event store once agent/tool traffic grows.

_Last update: 2026-08-28T03:02:45+02:00_

---

### ID: issue-017
- Date: 2026-08-28T03:07:05+02:00
- Severity: Medium
- Affected files:
  - src/investment_agents/domain/ledger.py
  - src/investment_agents/tools/google_sheets_ledger.py
  - src/investment_agents/agents/ledger_agent.py
  - src/investment_agents/core/config.py
  - docker-compose.yml
  - .env.example
  - requirements.txt
  - docs/ARCHITECTURE.md
  - README.md
  - tests/test_multi_agent_architecture.py
- Description: The Google Sheets ledger specialist still returned a placeholder even when configured, leaving the first analysis agent without a live data boundary or testable ledger interpretation logic.
- Action taken:
  - Added typed ledger parsing and summary logic for sheet rows, transactions, cash flow, fees, and positions.
  - Added service-account Google Sheets read support using `spreadsheets.values.get`.
  - Added `GOOGLE_LEDGER_RANGE` configuration, defaulting to `Ledger!A:Z`.
  - Updated the ledger agent to include structured `ledger_summary` metadata.
  - Added Google API client dependencies to `requirements.txt`.
  - Updated Docker/env/docs with ledger sheet/range setup and expected ledger columns.
  - Added tests for ledger row parsing, missing required columns, and mocked sheet summarization.
- Status: Fixed / Foundation
- Notes / Next steps:
  - Validate against the user's actual Google Sheet header names and refine aliases if needed.
  - Add realized/unrealized P/L once transaction semantics and current pricing sources are settled.

_Last update: 2026-08-28T03:07:05+02:00_

---

### ID: issue-018
- Date: 2026-08-28T08:07:56+02:00
- Severity: Low
- Affected files:
  - agent_api.py
  - README.md
- Description: Running `uvicorn` again produced `[WinError 10013] An attempt was made to access a socket in a way forbidden by its access permissions`.
- Action taken:
  - Confirmed port `8000` is not listed in the Windows TCP excluded port ranges.
  - Confirmed `127.0.0.1:8000` is already listening under Python PID `88080`.
  - Verified `GET http://127.0.0.1:8000/health` returns `{"status":"ok","model_id":"HuggingFaceTB/SmolLM2-360M-Instruct"}`.
- Status: Monitoring
- Notes / Next steps:
  - The API is already running on port `8000`; do not start a second `uvicorn` process on that same port.
  - To restart cleanly, stop PID `88080` first, then run `uvicorn agent_api:app --reload --port 8000`.
  - To run a second API instance, use another port such as `8001` and point Streamlit to that URL.

_Last update: 2026-08-28T08:07:56+02:00_

---

### ID: issue-019
- Date: 2026-08-28T08:15:59+02:00
- Severity: Medium
- Affected files:
  - src/investment_agents/core/config.py
  - src/investment_agents/domain/ledger.py
  - src/investment_agents/storage/market_cache.py
  - src/investment_agents/storage/__init__.py
  - src/investment_agents/tools/google_sheets_ledger.py
  - src/investment_agents/tools/registry.py
  - src/investment_agents/api/schemas.py
  - docker-compose.yml
  - .env.example
  - docs/ARCHITECTURE.md
  - README.md
  - tests/test_multi_agent_architecture.py
- Description: The ledger had become currency-aware, but it could not produce normalized reporting-currency totals for a mixed USD/GBP/ZAR portfolio.
- Action taken:
  - Added `REPORTING_CURRENCY` and `STATIC_FX_RATES` settings.
  - Added DuckDB-backed FX-rate storage alongside raw API payloads and curated snapshots.
  - Updated the Google Sheets ledger tool to use stored FX rates when summarizing cash flow and fees.
  - Updated ledger summaries to return source-currency totals, reporting-currency totals, rates used, and missing FX-rate pairs.
  - Expanded `/storage/status` with optional raw payload, curated snapshot, and FX-rate counts.
  - Updated Docker/env/docs to describe FX seeding and reporting-currency behavior.
  - Added tests for static FX config parsing, FX normalization, missing FX rates, cached FX retrieval, and ledger-tool integration.
- Status: Fixed / Foundation
- Verification:
  - `.venv\Scripts\python.exe -m unittest discover -s tests`: 18 tests passed.
  - `.venv\Scripts\python.exe -m py_compile ...`: passed for root launchers, `src`, and `tests`.
  - `docker compose config`: passed and includes `REPORTING_CURRENCY` / `STATIC_FX_RATES`.
- Notes / Next steps:
  - Replace static seeded rates with a scheduled Alpha Vantage or other FX ingestion path once quota policy is finalized.
  - Add historical transaction-date FX selection before reporting realized P/L by market movement versus currency movement.

_Last update: 2026-08-28T08:15:59+02:00_

---

### ID: issue-020
- Date: 2026-08-28T08:20:46+02:00
- Severity: Medium
- Affected files:
  - src/investment_agents/ui/streamlit_app.py
  - src/investment_agents/ui/observability.py
  - README.md
  - docs/ARCHITECTURE.md
  - tests/test_multi_agent_architecture.py
- Description: Observability events were available through FastAPI, but the Streamlit sandbox did not expose a usable view of orchestrator routing, specialist-agent results, or tool calls.
- Action taken:
  - Added Streamlit API helpers for `/observability/status` and `/observability/events`.
  - Added session-state tracking for the latest `trace_id`, routing decision, agent results, and trace events.
  - Added a Streamlit Trace tab with event, agent, and tool counts; routing JSON; an event timeline table; and agent-result details.
  - Expanded storage status display with raw payload, curated snapshot, and FX-rate counts when available.
  - Added pure UI helper functions for flattening trace events and counting trace participants.
  - Updated README and architecture docs to describe the trace viewer.
- Status: Fixed / Foundation
- Verification:
  - `.venv\Scripts\python.exe -m unittest discover -s tests`: 19 tests passed.
  - `.venv\Scripts\python.exe -m py_compile ...`: passed for root launchers, `src`, and `tests`.
  - `docker compose config`: passed.
- Notes / Next steps:
  - Add filtering by event type and selected agent once traces become longer.
  - Consider persisting selected traces into DuckDB if JSONL is not enough for dashboard-style observability.

_Last update: 2026-08-28T08:20:46+02:00_

---

### ID: issue-021
- Date: 2026-08-28T08:28:05+02:00
- Severity: Medium
- Affected files:
  - src/investment_agents/domain/portfolio.py
  - src/investment_agents/domain/__init__.py
  - src/investment_agents/tools/google_sheets_ledger.py
  - src/investment_agents/agents/ledger_agent.py
  - README.md
  - docs/ARCHITECTURE.md
  - tests/test_multi_agent_architecture.py
- Description: The Google Sheets adapter only understood transaction-ledger rows, but the project goal describes a holdings snapshot tab with ticker, shares held, current value, P/L, profit status, mixed currencies, and markets.
- Action taken:
  - Added holdings snapshot parsing for ticker, name, shares held, current price, purchase value, current value, P/L, profit status, currency, and market/exchange columns.
  - Added portfolio snapshot summaries for value and P/L by source currency.
  - Added FX-normalized reporting-currency holdings totals when stored rates are available.
  - Added allocation weights within each currency slice and concentration warnings for positions above 40%.
  - Added a snapshot-shape guard so ordinary transaction rows are not misread as holdings rows.
  - Updated the Google Sheets ledger tool to return both `ledger_summary` and `portfolio_summary`.
  - Updated the ledger agent metadata so orchestrator responses and the Streamlit Trace tab can inspect `portfolio_summary`.
  - Updated docs with the holdings snapshot format and concentration behavior.
- Status: Fixed / Foundation
- Verification:
  - `.venv\Scripts\python.exe -m unittest discover -s tests`: 22 tests passed.
  - `.venv\Scripts\python.exe -m py_compile ...`: passed for root launchers, `src`, and `tests`.
  - `docker compose config`: passed.
  - `git diff --check`: passed with only Windows line-ending notices.
- Notes / Next steps:
  - Validate aliases against the actual Google Sheet headers.
  - Add watchlist parsing and separate watchlist-vs-active-holdings behavior.
  - Add market-data enrichment over holdings symbols once API quota strategy is settled.

_Last update: 2026-08-28T08:28:05+02:00_

---

### ID: issue-022
- Date: 2026-08-28T08:33:49+02:00
- Severity: Medium
- Affected files:
  - src/investment_agents/core/config.py
  - src/investment_agents/domain/watchlist.py
  - src/investment_agents/domain/__init__.py
  - src/investment_agents/tools/google_sheets_ledger.py
  - src/investment_agents/agents/ledger_agent.py
  - .env.example
  - docker-compose.yml
  - README.md
  - docs/ARCHITECTURE.md
  - tests/test_multi_agent_architecture.py
- Description: The project goal calls for a watchlist vs. active-holdings split, but the Google Sheets integration had no watchlist domain model or optional range for a separate monitored-ideas tab.
- Action taken:
  - Added `GOOGLE_WATCHLIST_RANGE` as optional configuration.
  - Added a watchlist parser and summary model for symbols, names, currencies, markets, target/current prices, status, and reasons/notes.
  - Updated the Google Sheets ledger tool to fetch the optional watchlist range only when configured.
  - Added `watchlist_summary` to tool output and ledger-agent metadata.
  - Updated Docker/env/docs with watchlist setup and supported headers.
  - Added tests for watchlist parsing, missing symbol headers, optional Google range integration, and agent metadata forwarding.
- Status: Fixed / Foundation
- Verification:
  - `.venv\Scripts\python.exe -m unittest discover -s tests`: 25 tests passed.
  - `.venv\Scripts\python.exe -m py_compile ...`: passed for root launchers, `src`, and `tests`.
  - `docker compose config`: passed and includes `GOOGLE_WATCHLIST_RANGE`.
  - `git diff --check`: passed with only Windows line-ending notices.
- Notes / Next steps:
  - Validate supported watchlist aliases against the actual `Sheet10` headers.
  - Use watchlist symbols as candidate inputs for Finnhub/Alpha Vantage enrichment without mixing them into active-holdings exposure.

_Last update: 2026-08-28T08:33:49+02:00_

---

### ID: issue-023
- Date: 2026-08-28T08:40:35+02:00
- Severity: Medium
- Affected files:
  - src/investment_agents/core/config.py
  - src/investment_agents/agents/base.py
  - src/investment_agents/agents/routing.py
  - src/investment_agents/agents/orchestrator.py
  - src/investment_agents/agents/ledger_agent.py
  - src/investment_agents/agents/finnhub_agent.py
  - src/investment_agents/agents/alphavantage_agent.py
  - src/investment_agents/tools/registry.py
  - .env.example
  - docker-compose.yml
  - README.md
  - docs/ARCHITECTURE.md
  - tests/test_multi_agent_architecture.py
- Description: The ledger/watchlist tools could now discover portfolio and monitored symbols, but Finnhub and Alpha Vantage still only used explicit tickers from the question and otherwise fell back to an arbitrary `AAPL`.
- Action taken:
  - Added `MAX_ENRICHMENT_SYMBOLS` to cap symbol fan-out into market/research tools.
  - Updated the shared agent protocol to accept optional symbol hints.
  - Updated Finnhub and Alpha Vantage agents to analyze explicit user tickers first, then derived symbol hints, capped by configuration.
  - Removed the hard-coded `AAPL` fallback; specialists now return `needs_symbol` when no explicit or derived symbols are available.
  - Updated routing terms so watchlist and holdings questions select the ledger specialist.
  - Updated the orchestrator to run the ledger specialist first, derive symbols from `portfolio_summary` or `watchlist_summary`, emit a `symbol_context_derived` trace event, and pass symbols to Finnhub/Alpha Vantage.
  - Updated docs and Docker/env configuration.
- Status: Fixed / Foundation
- Verification:
  - `.venv\Scripts\python.exe -m unittest discover -s tests`: 28 tests passed.
  - `.venv\Scripts\python.exe -m py_compile ...`: passed for root launchers, `src`, and `tests`.
  - `docker compose config`: passed and includes `MAX_ENRICHMENT_SYMBOLS`.
  - `git diff --check`: passed with only Windows line-ending notices.
- Notes / Next steps:
  - Add exchange-aware symbol normalization before making live LSE/JSE requests.
  - Use cache freshness and provider capability metadata to choose Finnhub vs Alpha Vantage per symbol/market.

_Last update: 2026-08-28T08:40:35+02:00_

---

### ID: issue-024
- Date: 2026-08-28T08:45:01+02:00
- Severity: Medium
- Affected files:
  - src/investment_agents/core/config.py
  - src/investment_agents/tools/finnhub.py
  - src/investment_agents/tools/alphavantage.py
  - .env.example
  - docker-compose.yml
  - README.md
  - docs/ARCHITECTURE.md
  - tests/test_multi_agent_architecture.py
- Description: Derived portfolio/watchlist symbols could now fan out to market and research tools, but non-US holdings still needed provider-specific symbol aliases so LON/JSE symbols are not sent as plain US-style tickers.
- Action taken:
  - Added `FINNHUB_SYMBOL_ALIASES` and `ALPHAVANTAGE_SYMBOL_ALIASES` settings.
  - Updated Finnhub and Alpha Vantage tools to resolve aliases before cache lookup and API calls.
  - Preserved both `symbol` and `provider_symbol` in tool responses and curated cache snapshots.
  - Updated docs and Docker/env configuration with alias examples.
  - Added tests for alias parsing, aliased Finnhub cache keys, and aliased Alpha Vantage request params.
- Status: Fixed / Foundation
- Verification:
  - `.venv\Scripts\python.exe -m unittest discover -s tests`: 30 tests passed.
  - `.venv\Scripts\python.exe -m py_compile ...`: passed for root launchers, `src`, and `tests`.
  - `docker compose config`: passed and includes provider symbol alias settings.
  - `git diff --check`: passed with only Windows line-ending notices.
- Notes / Next steps:
  - Validate actual provider symbol formats for LON/JSE holdings before enabling live enrichment.
  - Consider storing provider capabilities by market so routing can choose Finnhub or Alpha Vantage per symbol.

_Last update: 2026-08-28T08:45:01+02:00_

---

### ID: issue-025
- Date: 2026-08-28T09:11:16+02:00
- Severity: Medium
- Affected files:
  - src/investment_agents/tools/provider_errors.py
  - src/investment_agents/tools/finnhub.py
  - src/investment_agents/tools/alphavantage.py
  - README.md
  - docs/ARCHITECTURE.md
  - tests/test_multi_agent_architecture.py
- Description: Provider request errors, rate limits, or malformed API payloads could still raise exceptions from Finnhub/Alpha Vantage and fail the whole chat request instead of gracefully degrading.
- Action taken:
  - Added shared provider error helpers for request failures, HTTP 429 rate limits, quota payloads, and malformed responses.
  - Updated Finnhub to return structured `ToolResult` statuses for provider errors, rate limits, and unreadable/non-object JSON.
  - Updated Alpha Vantage to return structured `ToolResult` statuses for provider errors, quota messages, unreadable/non-object JSON, and malformed `feed` payloads.
  - Avoided caching provider quota payloads as usable market/news data.
  - Updated tool readiness capabilities and docs to describe graceful provider degradation.
  - Added regression tests for Finnhub network failure, Finnhub HTTP 429, Alpha Vantage quota payloads, and malformed Alpha Vantage feed payloads.
- Status: Fixed / Foundation
- Verification:
  - `.venv\Scripts\python.exe -m unittest discover -s tests`: 34 tests passed.
  - `.venv\Scripts\python.exe -m py_compile ...`: passed for root launchers, `src`, and `tests`.
  - `docker compose config`: passed.
  - `git diff --check`: passed with only Windows line-ending notices.
- Notes / Next steps:
  - Add stale-cache fallback when a provider is unavailable but older cached data exists.
  - Expose provider error counts in the Streamlit Trace tab once traces grow longer.

_Last update: 2026-08-28T09:11:16+02:00_

---

### ID: issue-026
- Date: 2026-08-28T09:16:30+02:00
- Severity: Medium
- Affected files:
  - src/investment_agents/storage/market_cache.py
  - src/investment_agents/tools/finnhub.py
  - src/investment_agents/tools/alphavantage.py
  - README.md
  - docs/ARCHITECTURE.md
  - tests/test_multi_agent_architecture.py
- Description: Provider failures degraded into structured errors, but market/research tools could not yet fall back to older cached data when live provider calls failed after the fresh-cache TTL expired.
- Action taken:
  - Added `MarketDataCache.get_latest_raw_payload()` to retrieve the newest raw payload regardless of freshness.
  - Added optional `fetched_at` support to `store_raw_payload()` for deterministic cache tests.
  - Updated Finnhub to use stale cached quotes when provider errors, rate limits, or malformed responses occur.
  - Updated Alpha Vantage to use stale cached news/sentiment payloads when provider errors, quota payloads, or malformed responses occur.
  - Added `stale_cache` tool result status with `cache_status`, `stale_fetched_at`, and `degraded_from` metadata.
  - Updated tool readiness capabilities and docs with the fallback order.
  - Added regression tests for stale Finnhub quote fallback and stale Alpha Vantage news fallback.
- Status: Fixed / Foundation
- Verification:
  - `.venv\Scripts\python.exe -m unittest discover -s tests`: 36 tests passed.
  - `.venv\Scripts\python.exe -m py_compile ...`: passed for root launchers, `src`, and `tests`.
  - `docker compose config`: passed.
  - `git diff --check`: passed with only Windows line-ending notices.
- Notes / Next steps:
  - Expose stale-cache indicators more prominently in the Streamlit Trace tab.
  - Add source timestamps to any natural-language answer that relies on stale data.

_Last update: 2026-08-28T09:16:30+02:00_

---

### ID: issue-027
- Date: 2026-08-28T09:22:00+02:00
- Severity: Low
- Affected files:
  - agent_api.py
  - README.md
- Description: Running `uvicorn` produced `[WinError 10013] An attempt was made to access a socket in a way forbidden by its access permissions`.
- Action taken:
  - Confirmed Windows TCP excluded port ranges do not include `8000`.
  - Confirmed `127.0.0.1:8000` is already listening under Python PID `88080`.
  - Confirmed `127.0.0.1:8001` is also already listening under Python PID `70580`.
  - Verified both `http://127.0.0.1:8000/health` and `http://127.0.0.1:8001/health` return healthy API responses.
- Status: Monitoring
- Verification:
  - `netstat -ano | findstr :8000`: `127.0.0.1:8000 LISTENING 88080`.
  - `netstat -ano | findstr :8001`: `127.0.0.1:8001 LISTENING 70580`.
  - `Invoke-RestMethod http://127.0.0.1:8000/health`: returned `status: ok`.
  - `Invoke-RestMethod http://127.0.0.1:8001/health`: returned `status: ok`.
- Notes / Next steps:
  - Reuse the already-running API instead of starting another `uvicorn` process on the same port.
  - To restart cleanly, stop the existing Python process for the target port first.
  - To run another API copy, use an open port such as `8080` and point Streamlit's `AGENT_API_URL` to that port.

_Last update: 2026-08-28T09:22:00+02:00_

---

### ID: issue-028
- Date: 2026-08-28T09:30:00+02:00
- Severity: Medium
- Affected files:
  - src/investment_agents/core/config.py
  - src/investment_agents/domain/portfolio.py
  - src/investment_agents/domain/__init__.py
  - src/investment_agents/tools/google_sheets_ledger.py
  - src/investment_agents/ui/observability.py
  - src/investment_agents/ui/streamlit_app.py
  - .env.example
  - docker-compose.yml
  - README.md
  - docs/ARCHITECTURE.md
  - tests/test_multi_agent_architecture.py
- Description: The holdings snapshot could calculate concentration warnings, but the platform did not yet return configurable structured alerts for concentration and position losses or surface them clearly in the Streamlit trace workflow.
- Action taken:
  - Added `CONCENTRATION_ALERT_THRESHOLD` and `LOSS_ALERT_THRESHOLD` settings.
  - Added structured `PortfolioAlert` records to holdings summaries for concentration and unrealized-loss thresholds.
  - Passed configured thresholds through the Google Sheets ledger tool.
  - Preserved legacy concentration warning messages while adding `portfolio_summary.alerts`.
  - Added Streamlit Trace tab alert extraction, alert count, and a portfolio-alerts table with percentage formatting.
  - Updated env, Docker, README, architecture docs, and regression tests.
- Status: Fixed / Foundation
- Verification:
  - `.venv\Scripts\python.exe -m unittest discover -s tests`: 38 tests passed.
  - `.venv\Scripts\python.exe -m py_compile ...`: passed for root launchers, `src`, and `tests`.
  - `docker compose config`: passed and includes alert threshold environment settings.
  - `git diff --check`: passed with only Windows line-ending notices.
- Notes / Next steps:
  - Add alert filtering and severity grouping once the Streamlit Trace tab has more event volume.
  - Route stale-cache and provider-failure statuses into the same monitoring surface as portfolio alerts.

_Last update: 2026-08-28T09:30:00+02:00_

---

### ID: issue-029
- Date: 2026-08-28T09:32:42+02:00
- Severity: Medium
- Affected files:
  - src/investment_agents/ui/observability.py
  - src/investment_agents/ui/streamlit_app.py
  - README.md
  - docs/ARCHITECTURE.md
  - tests/test_multi_agent_architecture.py
- Description: Provider failures, stale-cache fallbacks, missing ticker symbols, and configuration gaps were present in agent/tool results but were still too buried in raw JSON for practical Streamlit monitoring.
- Action taken:
  - Added data-source status row extraction from agent `tool_calls`.
  - Added skipped-agent fallback rows for metadata statuses such as `needs_symbol`.
  - Added a data-warning count for statuses that need attention.
  - Added a Streamlit Trace tab data-source status table with provider symbol, cache state, stale timestamp, degraded-from status, and summary columns.
  - Updated README and architecture docs to describe provider/degraded-data visibility.
  - Added regression coverage for stale-cache and skipped-agent status display.
- Status: Fixed / Foundation
- Verification:
  - `.venv\Scripts\python.exe -m unittest discover -s tests`: 39 tests passed.
  - `.venv\Scripts\python.exe -m py_compile ...`: passed for root launchers, `src`, and `tests`.
  - `docker compose config`: passed.
  - `git diff --check`: passed with only Windows line-ending notices.
- Notes / Next steps:
  - Add filters by status/agent once traces have more rows.
  - Consider source timestamp callouts in natural-language answers that rely on stale cached provider data.

_Last update: 2026-08-28T09:32:42+02:00_

---

### ID: issue-030
- Date: 2026-08-28T09:37:21+02:00
- Severity: Medium
- Affected files:
  - src/investment_agents/agents/orchestrator.py
  - README.md
  - docs/ARCHITECTURE.md
  - tests/test_multi_agent_architecture.py
- Description: Degraded provider results and stale-cache timestamps were visible in trace metadata, but the natural-language `reply` did not call them out for API clients that do not inspect raw `agent_results`.
- Action taken:
  - Added orchestrator source-status notes for stale cache, rate limits, provider errors, malformed responses, missing configuration, and missing symbols.
  - Added stale-cache notes that include provider symbol, cache timestamp, and degraded-from status.
  - Inserted a `Data/source notes` section into synthesized replies only when selected specialist results need attention.
  - Updated README and architecture docs to describe answer-level data-source transparency.
  - Added regression coverage proving stale provider source notes appear in synthesized replies.
  - Fixed a caught indentation error in the new orchestrator synthesis path before final validation.
- Status: Fixed / Foundation
- Verification:
  - `.venv\Scripts\python.exe -m unittest discover -s tests`: 40 tests passed.
  - `.venv\Scripts\python.exe -m py_compile ...`: passed for root launchers, `src`, and `tests`.
  - `docker compose config`: passed.
  - `git diff --check`: passed with only Windows line-ending notices.
- Notes / Next steps:
  - Consider promoting source notes into a structured `source_notes` API field if the future React UI needs them without parsing `reply`.
  - Add source timestamps for successful live/fresh-cache provider results once quote/news normalization stores display-ready timestamps.

_Last update: 2026-08-28T09:37:21+02:00_

---

### ID: issue-031
- Date: 2026-08-28T09:43:46+02:00
- Severity: Medium
- Affected files:
  - src/investment_agents/agents/orchestrator.py
  - src/investment_agents/api/app.py
  - src/investment_agents/api/schemas.py
  - src/investment_agents/ui/observability.py
  - src/investment_agents/ui/streamlit_app.py
  - README.md
  - docs/ARCHITECTURE.md
  - tests/test_multi_agent_architecture.py
- Description: Degraded source context was present in the natural-language reply, but React or other API clients would still need to parse prose to render source/degradation UI.
- Action taken:
  - Added a structured `SourceNote` dataclass to the orchestrator.
  - Added `source_notes` to `OrchestratorResponse` and FastAPI `ChatResponse`.
  - Returned source notes from `/chat` alongside `reply`, `agent_results`, and `routing_decision`.
  - Updated Streamlit session state and Trace tab rendering to use the structured `source_notes` field directly.
  - Added helper formatting for source-note rows.
  - Updated README and architecture docs to describe the structured API contract.
  - Added regression coverage for source-note serialization and Streamlit row formatting.
- Status: Fixed / Foundation
- Verification:
  - `.venv\Scripts\python.exe -m unittest discover -s tests`: 40 tests passed.
  - `.venv\Scripts\python.exe -m py_compile ...`: passed for root launchers, `src`, and `tests`.
  - `docker compose config`: passed.
  - `git diff --check`: passed with only Windows line-ending notices.
- Notes / Next steps:
  - Add source timestamps for successful live/fresh-cache provider results once normalized quote/news records include display-ready timestamps.
  - Consider a typed Pydantic `SourceNoteCard` once the source-note schema stabilizes further.

_Last update: 2026-08-28T09:43:46+02:00_

---

### ID: issue-032
- Date: 2026-09-05T21:46:29+02:00
- Severity: Medium
- Affected files:
  - first_agent.py
  - src/investment_agents/cli.py
  - src/investment_agents/core/config.py
  - src/investment_agents/tools/finnhub.py
  - src/investment_agents/tools/alphavantage.py
  - src/investment_agents/agents/orchestrator.py
  - src/investment_agents/ui/observability.py
  - README.md
  - docs/ARCHITECTURE.md
  - tests/test_multi_agent_architecture.py
- Description: The CLI appeared to work while the Streamlit app looked stale, and the agent had no live access to Google Sheets, Finnhub, Alpha Vantage, Yahoo Finance, or Google Finance.
- Evidence:
  - `GET http://127.0.0.1:8000/health`: FastAPI was running on port 8000.
  - `GET http://127.0.0.1:8000/tools/readiness`: Google Sheets, Finnhub, and Alpha Vantage all returned `needs_configuration`.
  - Project root check: no `.env` file was present, so provider credentials and Google Sheets settings were unavailable.
  - `POST http://127.0.0.1:8000/chat`: backend chat endpoint routed correctly to all three specialists and returned structured `source_notes`, but each selected source degraded to missing-configuration notes.
  - Port check: FastAPI listened on `127.0.0.1:8000`; Streamlit listened on `0.0.0.0:8501`.
- Action taken:
  - Changed shared settings loading so `core/config.py` reads a project-local `.env` before building the tool registry.
  - Updated `first_agent.py` and `src/investment_agents/cli.py` so the default CLI runs the investment orchestrator and the old local Hugging Face chat remains available with `--local-llm`.
  - Added `fetched_at` metadata to fresh/live/stale Finnhub and Alpha Vantage tool results and carried it into orchestrator source notes.
  - Added `source_at` formatting to Streamlit observability rows for provider-result timestamps.
  - Updated README and architecture docs to clarify missing configuration, restart requirements, and that Yahoo Finance/Google Finance are not current providers.
  - Added regression coverage for `.env` loading, CLI exports, source timestamps, and provider timestamp propagation.
- Status: Fixed / Foundation
- Verification:
  - `.venv\Scripts\python.exe -m unittest discover -s tests`: 42 tests passed.
  - `.venv\Scripts\python.exe -m py_compile ...`: passed for root launchers and changed modules.
  - `docker compose config`: passed and showed blank provider env values until `.env` is filled.
  - `git diff --check`: passed with only Windows line-ending notices.
  - `POST http://127.0.0.1:8000/chat`: passed and returned routed specialist results plus missing-configuration source notes.
- Notes / Next steps:
  - Create `.env` from `.env.example`, fill Google Sheets service-account settings plus Finnhub and Alpha Vantage keys, then restart FastAPI and Streamlit.
  - Add Yahoo Finance as an optional fallback provider only if it becomes part of the planned provider set; Google Finance should not be treated as an official API-backed integration.

_Last update: 2026-09-05T21:46:29+02:00_

## 2026-09-15 - Documentation Reconciled With Runtime

- Status: documentation updated; runtime limitations remain open.
- Scope: README, architecture, blueprint, research prompt, and both reference docs.
- Evidence: source search shows Transformers pipeline usage, keyword routing and
  template synthesis; LangChain/LangGraph occur only in dependency declarations.
- Changes: documented exact current prompt, Streamlit history behavior, environment
  configuration boundaries, local port 8001 versus Docker port 8000, and test scope.
- Historical verification: earlier local checks returned HTTP 200 for API health on
  8001 and Streamlit health on 8501; a no-ticker research request returned a trace
  and needs-symbol reply. The user subsequently reported research working.
- Docker: earlier diagnostic build was intentionally stopped during base-image
  setup; no successful full build or reproduction of the original error is recorded.
- Verification for this update: source/document review only; no new application,
  model, browser, or Docker tests. Previous test results remain historical.
- Follow-up: implement evidence-based model synthesis and LangGraph before claiming
  either is operational. Verify full Docker build and browser chat independently.

_Documentation reconciliation: 2026-09-15. Earlier entries above are historical._

## 2026-11-01 - Bounded Observability Retention

- Status: implemented; local verification passed.
- Severity: Medium.
- Affected files: `src/investment_agents/core/observability.py`,
  `src/investment_agents/core/config.py`, `src/investment_agents/api/app.py`,
  `docker-compose.yml`, `.env.example`, `docs/SETUP.md`, and
  `tests/test_multi_agent_architecture.py`.
- Finding: Persistent JSONL observability events grew without limit, and listing
  recent events parsed the full log on each request. Events are intentionally
  retained to support personal agent analysis and improvement.
- Action taken:
  - Added size-based JSONL rotation with a 10 MiB active log and five retained
    backups by default (about 60 MiB total); both limits are configurable.
  - Kept trace-ID lookups searching all retained log segments.
  - Changed unfiltered event listing to read only the newest events needed for
    the response.
  - Ensured clearing persisted logs removes the active file and its backups.
- Verification: focused architecture and observability test suite and
  `docker compose config` passed.
- Notes: Increase `OBSERVABILITY_MAX_BYTES` and/or
  `OBSERVABILITY_BACKUP_COUNT` in `.env` if a longer local history is needed.

## 2026-11-01 - Streamlit API Flow Default

- Status: fixed; regression test added.
- Severity: Medium.
- Affected files: `src/investment_agents/ui/streamlit_app.py`,
  `src/investment_agents/core/config.py`, `.env.example`, `README.md`,
  `docs/SETUP.md`, and `tests/test_multi_agent_architecture.py`.
- Finding: The local CLI invokes the orchestrator directly, but Streamlit depends
  on the FastAPI service. Streamlit defaulted to `http://localhost:8000` while
  local setup instructions run the API on port `8001`, so the UI could not reach
  the working agent unless the endpoint was manually changed.
- Action taken:
  - Aligned the Streamlit and shared settings defaults and `.env.example` with
    the documented local API port 8001. Docker continues to set its internal
    API endpoint explicitly to `http://api:8000`.
  - Migrated existing Streamlit session state using the former localhost:8000
    default to the new local default.
  - Added an actionable API startup/URL hint when a chat request cannot connect.
  - Updated setup documentation and added a settings-default regression test.
- Notes: If FastAPI is running on another port, set `AGENT_API_URL` or update
  the sidebar URL.

## 2026-11-01 - Market Query Routing and Trace Rendering

- Status: routing fix and UI rendering fix implemented; regression tests pass.
- Severity: Medium.
- Affected files: `src/investment_agents/agents/routing.py`,
  `src/investment_agents/ui/streamlit_app.py`, and
  `tests/test_multi_agent_architecture.py`.
- Findings:
  - The market query “What are the latest market trends for AAPL?” was
    incorrectly routed to the ledger agent because the ledger keyword `pl`
    matched inside `AAPL`.
  - The API recorded trace events, but the Streamlit Trace tab was rendered
    before the chat submission updated session state, leaving the view empty
    until a later rerun.
  - During the market-query test, Finnhub returned a quote, Alpha Vantage was
    rate-limited and fell back to cached news dated 2026-09-27, and web search
    returned no source-linked results. “Latest” answers must not imply that
    these stale or missing sources are current.
- Actions taken:
  - Changed router keyword matching to token boundaries and added an AAPL
    regression test.
  - Process chat submissions before rendering the Chat and Trace tabs, so the
    new trace and elapsed-time caption are available in the same render.
  - Kept chat responses visible if fetching trace events fails, and surface
    that trace-fetch error separately.
  - Added an AppTest regression test confirming a successful chat submission
    stores and renders its trace before the tab contents are created.
- Verification: all 51 tests passed, including the routing and UI regression
  tests; Python compilation and `git diff --check` passed. The local API health
  endpoint returned healthy and the Streamlit health endpoint returned `ok` on
  port 8502. A second live browser submission was inconclusive because the
  integrated browser could not stabilize the submit control; the AppTest
  regression covers the ordering/state bug.
- Follow-up: ensure provider responses clearly distinguish fresh data, stale
  cache, rate limits, and absent search sources before presenting market
  conclusions.
