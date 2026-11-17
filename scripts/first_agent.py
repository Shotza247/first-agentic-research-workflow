from __future__ import annotations

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from investment_agents.core.chat import (  # noqa: E402,F401
    AgentResponse,
    ChatMessage,
    FirstAgent,
    create_text_generation_pipeline,
    initial_chat,
    parse_pipeline_response,
    run_cli as run_local_llm_cli,
)
from investment_agents.cli import main, run_orchestrator_cli  # noqa: E402,F401


if __name__ == "__main__":
    main()
