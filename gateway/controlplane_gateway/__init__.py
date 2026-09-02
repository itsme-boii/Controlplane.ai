"""ControlPlane.ai gateway service.

An OpenAI-compatible proxy that sits inline between enterprise AI apps and the
foundation models they call. Phase 1 is passthrough only: resolve config,
forward the call, log an audit record. Checks and policy land in later phases.
"""

__version__ = "0.1.0"
