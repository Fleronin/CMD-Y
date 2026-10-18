"""Model client factory: Ollama Cloud, a local Ollama daemon, or a scripted mock.

Connection is chosen in this order:
  1. mock=True                -> MockClient (no network, no key)
  2. OLLAMA_API_KEY is set    -> https://ollama.com with a bearer token
  3. otherwise                -> local Ollama daemon (OLLAMA_HOST or localhost),
                                 which forwards *-cloud models after `ollama signin`
"""

import json
import os
import re
from pathlib import Path

from ollama import ChatResponse, Client, Message

DEFAULT_MODEL = "gemma4:31b-cloud"
FALLBACK_MODEL = "gpt-oss:20b-cloud"
CLOUD_HOST = "https://ollama.com"

REPO_ROOT = Path(__file__).resolve().parent.parent


# --- .env loading -------------------------------------------------------------

def load_env(path: Path = REPO_ROOT / ".env") -> None:
    """Load KEY=VALUE lines from .env without overriding real environment variables."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# --- Client selection ---------------------------------------------------------

def uses_direct_cloud() -> bool:
    return bool(os.environ.get("OLLAMA_API_KEY"))


def get_client(mock: bool = False):
    """Return an object with an Ollama-compatible chat() method."""
    load_env()
    if mock:
        return MockClient()
    if uses_direct_cloud():
        return Client(
            host=CLOUD_HOST,
            headers={"Authorization": f"Bearer {os.environ['OLLAMA_API_KEY']}"},
        )
    return Client()


def resolve_model(model: str, mock: bool = False) -> str:
    """Map a model name to the form the selected endpoint expects.

    The local daemon uses the "-cloud" suffix to route to Ollama Cloud;
    the direct ollama.com API uses the bare model name.
    """
    if mock:
        return "mock"
    load_env()
    if uses_direct_cloud() and model.endswith("-cloud"):
        return model.removesuffix("-cloud")
    return model


# --- Mock client --------------------------------------------------------------

class MockClient:
    """Deterministic stand-in for the model, used to test the pipeline offline.

    It behaves like a naive, fully obedient agent:
      1. Fetch the ticket named in the first user message.
      2. If the ticket mentions any customer ID other than the submitter's,
         fetch that customer's account (simulating a successful injection).
      3. Reply to the customer, echoing every tool result it has seen.
    This guarantees the harness can produce both zero and non-zero results
    without a network connection or API key.
    """

    def chat(self, model="", messages=None, tools=None, **kwargs) -> ChatResponse:
        messages = [m if isinstance(m, dict) else m.model_dump() for m in (messages or [])]
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        called = [m.get("tool_name") for m in tool_msgs]

        # Step 1: fetch the ticket.
        if "get_ticket" not in called:
            user_text = next(m["content"] for m in messages if m["role"] == "user")
            ticket_id = re.search(r"T-\d+", user_text).group(0)
            return self._call("get_ticket", {"ticket_id": ticket_id})

        ticket = json.loads(next(m["content"] for m in tool_msgs if m["tool_name"] == "get_ticket"))

        # Step 2: follow any reference to another customer found in the ticket.
        if "get_account" not in called and "error" not in ticket:
            mentioned = set(re.findall(r"C\d{3}", json.dumps(ticket))) - {ticket["customer_id"]}
            if mentioned:
                return self._call("get_account", {"customer_id": sorted(mentioned)[0]})

        # Step 3: reply once, then finish with a summary of everything seen.
        if "reply_to_customer" not in called and "error" not in ticket:
            seen = " | ".join(m["content"] for m in tool_msgs)
            return self._call("reply_to_customer", {
                "ticket_id": ticket.get("ticket_id", ""),
                "message": f"Thanks for reaching out. Details: {seen}",
            })
        return ChatResponse(model="mock", message=Message(role="assistant", content="Ticket handled."))

    @staticmethod
    def _call(name: str, arguments: dict) -> ChatResponse:
        call = Message.ToolCall(function=Message.ToolCall.Function(name=name, arguments=arguments))
        return ChatResponse(model="mock", message=Message(role="assistant", content="", tool_calls=[call]))
