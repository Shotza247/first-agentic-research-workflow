from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Callable

from dotenv import load_dotenv

from investment_agents.core.messages import (
    DEFAULT_MAX_NEW_TOKENS,
    DEFAULT_MODEL_ID,
    DEFAULT_SYSTEM_PROMPT,
    ChatMessage,
    initial_chat,
)

WarningHandler = Callable[[str], None]


@dataclass
class AgentResponse:
    """Structured result returned by the reusable chat model layer."""

    chat: list[ChatMessage]
    reply: str
    elapsed_seconds: float
    raw_response: Any = field(repr=False, default=None)


def ensure_runtime_dependencies() -> None:
    """Fail early with a clear message when local model dependencies are missing."""
    try:
        import torchvision  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency 'torchvision'. Some models or pipeline code require it.\n"
            "If you're on a CPU-only machine, run:\n"
            "  pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu\n"
            "Or use the command from https://pytorch.org/get-started/locally/ "
            "appropriate for your platform."
        ) from exc


def load_huggingface_token(
    hf_token: str | None = None,
    warn: WarningHandler | None = None,
) -> str | None:
    """Load and optionally register a Hugging Face token."""
    load_dotenv()
    token = hf_token or os.getenv("HF_TOKEN")
    if not token:
        return None

    try:
        from huggingface_hub import login

        login(token=token)
    except Exception as exc:  # pragma: no cover - depends on local HF state/network.
        if warn:
            warn(f"HF login failed: {exc}")
        else:
            raise

    return token


def create_text_generation_pipeline(
    model_id: str = DEFAULT_MODEL_ID,
    hf_token: str | None = None,
    warn: WarningHandler | None = None,
):
    """Create the local text-generation pipeline used by frontends and agents."""
    ensure_runtime_dependencies()
    load_huggingface_token(hf_token=hf_token, warn=warn)
    from transformers import pipeline

    return pipeline(task="text-generation", model=model_id, dtype="auto")


def parse_pipeline_response(
    response: Any,
    chat: list[ChatMessage],
) -> tuple[list[ChatMessage], str]:
    """Normalize common transformers pipeline response shapes into chat + reply."""
    first = response[0] if isinstance(response, list) and response else response

    if isinstance(first, dict):
        generated = (
            first.get("generated_text")
            or first.get("text")
            or first.get("summary_text")
        )
    else:
        generated = first

    if isinstance(generated, list):
        next_chat = generated
        last_message = next_chat[-1] if next_chat else {}
        if isinstance(last_message, dict):
            reply = str(last_message.get("content") or last_message.get("text") or "")
        else:
            reply = str(last_message)
        return next_chat, reply

    if isinstance(generated, str):
        next_chat = [*chat, {"role": "assistant", "content": generated}]
        return next_chat, generated

    reply = str(generated)
    next_chat = [*chat, {"role": "assistant", "content": reply}]
    return next_chat, reply


class FirstAgent:
    """Reusable local LLM wrapper for CLI, API, Streamlit, or specialist agents."""

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        pipe: Any | None = None,
        warn: WarningHandler | None = None,
    ) -> None:
        self.model_id = model_id
        self.max_new_tokens = max_new_tokens
        self.system_prompt = system_prompt
        self._pipe = pipe
        self._warn = warn

    @property
    def pipe(self):
        if self._pipe is None:
            self._pipe = create_text_generation_pipeline(
                model_id=self.model_id,
                warn=self._warn,
            )
        return self._pipe

    def new_chat(self) -> list[ChatMessage]:
        return initial_chat(self.system_prompt)

    def respond(
        self,
        user_input: str,
        chat: list[ChatMessage] | None = None,
        max_new_tokens: int | None = None,
    ) -> AgentResponse:
        user_input = user_input.strip()
        if not user_input:
            raise ValueError("user_input cannot be empty")

        next_chat = list(chat or self.new_chat())
        next_chat.append({"role": "user", "content": user_input})

        start = perf_counter()
        raw_response = self.pipe(
            next_chat,
            max_new_tokens=max_new_tokens or self.max_new_tokens,
        )
        elapsed = perf_counter() - start

        parsed_chat, reply = parse_pipeline_response(raw_response, next_chat)
        return AgentResponse(
            chat=parsed_chat,
            reply=reply,
            elapsed_seconds=elapsed,
            raw_response=raw_response,
        )


def run_cli() -> None:
    """Run a terminal chat loop using the reusable agent."""

    def warn(message: str) -> None:
        print(f"Warning: {message}")

    print(f"Loading {DEFAULT_MODEL_ID} (first run downloads the model, ~1-2 min)...")
    try:
        agent = FirstAgent(warn=warn)
        chat = agent.new_chat()
        _ = agent.pipe
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)

    if not os.getenv("HF_TOKEN"):
        print("No HF_TOKEN set - continuing without login (fine for public models).\n")

    print("Agent ready! Type a question, or 'quit' to stop.\n")

    while True:
        try:
            user_input = input("> ").strip()
            if user_input.lower() in {"quit", "exit"}:
                print("Goodbye!")
                break
            if not user_input:
                continue

            try:
                result = agent.respond(user_input, chat=chat)
            except Exception as exc:
                print(f"Model error: {exc}")
                continue

            chat = result.chat
            print(f"\nAgent: {result.reply}\n")
            print(f"(Response time: {result.elapsed_seconds:.2f} seconds)\n")

        except KeyboardInterrupt:
            print("\n(Stopped) Goodbye!")
            break
