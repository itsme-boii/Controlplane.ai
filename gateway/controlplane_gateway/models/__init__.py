"""Foundation-model providers behind one interface.

Adding a provider (Ollama, an OpenAI-compatible endpoint, Claude) means adding a
module here and a branch in ``build_provider`` — nothing else in the gateway
changes.
"""

from __future__ import annotations

from controlplane_gateway.config import Settings
from controlplane_gateway.models.base import ModelProvider, ProviderError
from controlplane_gateway.models.groq import GroqProvider

__all__ = ["ModelProvider", "ProviderError", "build_provider"]


def build_provider(settings: Settings) -> ModelProvider:
    provider = settings.model_provider.lower()
    if provider == "groq":
        return GroqProvider(settings)
    raise ProviderError(f"unknown MODEL_PROVIDER: {settings.model_provider!r}")
