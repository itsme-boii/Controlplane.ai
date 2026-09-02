"""Process-wide singletons for the heavy ML models the detectors share.

Each model is loaded once on first use and reused. A load failure propagates —
it is never swallowed here; the calling detector turns it into an ``ok=False``
DetectionResult so the decision engine escalates to review (no-false-fallback).
"""

from __future__ import annotations

import functools
import threading
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")


def _singleton(factory: Callable[[], T]) -> Callable[[], T]:
    """Wrap a zero-arg factory so it runs at most once, even under threads."""
    holder: dict[str, T] = {}
    lock = threading.Lock()

    @functools.wraps(factory)
    def get() -> T:
        if "value" not in holder:
            with lock:
                if "value" not in holder:
                    holder["value"] = factory()
        return holder["value"]

    return get


@_singleton
def spacy_nlp() -> Any:
    """en_core_web_lg — shared by Presidio's NLP engine and claim segmentation."""
    import spacy

    return spacy.load("en_core_web_lg")


@_singleton
def presidio_analyzer() -> Any:
    from presidio_analyzer import AnalyzerEngine
    from presidio_analyzer.nlp_engine import NlpEngineProvider

    provider = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": "en_core_web_lg"}],
        }
    )
    return AnalyzerEngine(nlp_engine=provider.create_engine(), supported_languages=["en"])


@_singleton
def detoxify_model() -> Any:
    """Detoxify 'unbiased-small' — toxicity probabilities with reduced identity-term bias."""
    from detoxify import Detoxify

    return Detoxify("unbiased-small")


@_singleton
def regard_classifier() -> Any:
    """HF regardv3 — the model behind the `regard` fairness metric."""
    from transformers import pipeline

    return pipeline(
        "text-classification",
        model="sasha/regardv3",
        top_k=None,
        truncation=True,
    )


@_singleton
def nli_cross_encoder() -> Any:
    """Cross-encoder NLI — labels: contradiction / entailment / neutral."""
    from sentence_transformers import CrossEncoder

    return CrossEncoder("cross-encoder/nli-deberta-v3-xsmall")


@_singleton
def injection_embedder() -> Any:
    """Sentence transformer for injection similarity."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")


@_singleton
def injection_bank_embeddings() -> Any:
    """Pre-computed embeddings for the injection prompt bank."""
    import json
    import os

    bank_path = os.path.join(os.path.dirname(__file__), "data", "injection_bank.json")
    with open(bank_path, encoding="utf-8") as f:
        prompts = json.load(f)

    embedder = injection_embedder()
    return embedder.encode(prompts, convert_to_tensor=True)
