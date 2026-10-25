"""Model providers. The core ships an OpenAI-compatible adapter (DeepInfra, OpenAI, NIM, vLLM, Ollama, gateways)
and a scripted stub for tests; Anthropic and LangChain adapters are optional extras."""

from .base import ChatModel
from .openai_compat import OpenAICompatible
from .stub import StubModel

__all__ = ["ChatModel", "OpenAICompatible", "StubModel"]
