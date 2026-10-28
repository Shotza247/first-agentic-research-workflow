---
noteId: "0fa10530acf211f18d028128fd438deb"
tags: []

---

# Research Agent

A Python research-agent project with CLI, FastAPI, and Streamlit entry points.
The current product scope is one research agent. LangGraph planning and LLM
synthesis are proposed next steps, not implemented capabilities.

The repository also contains earlier investment-analysis scaffolding. The default
CLI and API still use keyword routing and template summaries. Local Hugging Face
chat runs separately with `--local-llm`.

Documentation reconciled with source on 2026-09-16. LangChain,
`langchain-huggingface`, and LangGraph are declared dependencies only: the runtime
does not import them or construct a graph. The local model uses Transformers.

## Project Map

- [Architecture and folder responsibilities](docs/ARCHITECTURE.md)
- [Exact system prompt and where it applies](docs/RESEARCH_PROMPT.md)
- [Setup, Google Sheets, and provider configuration](docs/SETUP.md)
- [Investigation history](AUDIT_LOG.md)

```text
first_agent.py           CLI launcher and compatibility imports
agent_api.py             FastAPI launcher
streamlit_frontend.py    Streamlit launcher
src/investment_agents/   Existing Python package
tests/                  Automated behavior and API contract tests
docs/                   Architecture, setup, and system-prompt documentation
```

## Run

Use the existing virtual environment, or follow the
[setup instructions](docs/SETUP.md#install).
Create `.env` from `.env.example` only if it does not already exist.

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

`.env.example` is a template, not a loaded configuration file. Never put real keys
in that template. Provider keys enable the existing adapters; `OPENAI_API_KEY`,
`OPENAI_MODEL`, `LLM_PROVIDER`, and `LLM_MAX_OUTPUT_TOKENS` are currently unused by
the response-generation path. Setting them does not activate an LLM in the API.

In one terminal, start FastAPI:

```powershell
.venv\Scripts\python.exe -m uvicorn agent_api:app --reload --port 8001
```

In another terminal, point Streamlit at that API:

```powershell
$env:AGENT_API_URL = "http://localhost:8001"
.venv\Scripts\python.exe -m streamlit run streamlit_frontend.py --server.port 8501
```

API docs: http://localhost:8001/docs. Streamlit normally opens at
http://localhost:8501. Port 8001 is an alternative to the previously blocked 8000;
local Windows port restrictions may still apply.

Run the existing default CLI with `.venv\Scripts\python.exe first_agent.py`.
Add `--local-llm` for the separate local model chat.

To restart, press Ctrl+C in each service terminal and run its command again.
Use **Clear conversation** in Streamlit to reset an old session's system message.
The Streamlit API URL is read from the process environment or sidebar, so use the
explicit environment assignment above rather than relying on `.env` for this UI setting.

## Quick Checks

Open http://localhost:8001/docs or use PowerShell:

```powershell
Invoke-RestMethod http://localhost:8001/health
Invoke-RestMethod http://localhost:8001/tools/readiness
$body = @{ message = "Research news sentiment" } | ConvertTo-Json
$result = Invoke-RestMethod http://localhost:8001/chat -Method Post -ContentType "application/json" -Body $body
$result.reply
$result.trace_id
```

Try `What are the current market trends around the USD?` to exercise web search,
Finnhub exchange rates, and Alpha Vantage macro news. Try `Research AAPL news
sentiment` for ticker-specific data. Replies include numbered links to retrieved
evidence; unavailable or stale provider data is called out explicitly. In
Streamlit, check the sidebar API URL, send the same prompts, and inspect the Trace
tab. Readiness means settings are present, not that credentials or live provider
access have been validated.

The first uncached provider request can take longer than a repeat request because
the result is then cached in DuckDB. Configure `PROVIDER_REQUEST_TIMEOUT_SECONDS`
in `.env` to limit provider connection/read waits; it defaults to `10`. If a
response cannot be rendered, Streamlit displays an error instead of leaving the
page blank. See [provider configuration](docs/SETUP.md#storage-and-reporting).

## Docker Status

Docker files exist, but a successful full build has not been verified in the latest
investigation. The diagnostic build was stopped during base-image setup; the user's
original build failure remains unresolved. Capture a full attempt with
`docker compose --progress plain build`.

Compose publishes API port 8000 and UI port 8501; its Streamlit service uses
`http://api:8000` internally. These differ from the local API command above.
Avoid running local and Docker UIs on the same host port. A Windows service-account
path is not usable inside Linux containers without mounting the file and configuring
its container path. The supplied Compose file does not mount that credential file.

## Tests

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Passing tests establishes behavior for their inputs and fixtures. Live provider
access, real model answer quality, and browser chat require separate checks.

The existing suite covers ticker routing, ledger/watchlist parsing, FX, cache
behavior, provider failures, trace helpers, and API contracts. It does not test a
LangGraph workflow or LLM synthesis because those are not implemented. Historical
test results are recorded in the audit log; they are not fresh verification.
