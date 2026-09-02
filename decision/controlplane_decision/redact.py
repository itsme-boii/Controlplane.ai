"""The transform behind the ``edit`` tier: mask PII spans in place.

Given the exact text that was analysed and the spans a detector flagged, replace
each in-scope span with a mask of the policy's ``mask_char``. Spans are applied
right to left so earlier offsets stay valid. Only entity types listed in
``policy.pii.entities`` are masked (an empty list means "mask every PII type").
"""

from __future__ import annotations

from controlplane_detectors import Span
from controlplane_policy import PiiHandling
from pydantic import BaseModel, Field


class MaskedSpan(BaseModel):
    start: int
    end: int
    label: str | None
    original: str


class RedactionOutcome(BaseModel):
    text: str
    masked: list[MaskedSpan] = Field(default_factory=list)
    # Spans that were flagged but left untouched because their entity type is
    # not in the policy's edit scope — surfaced, not hidden.
    skipped_labels: list[str] = Field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.masked)


def redact_spans(text: str, spans: list[Span], pii: PiiHandling) -> RedactionOutcome:
    in_scope = set(pii.entities)

    def wanted(span: Span) -> bool:
        if not in_scope:
            return True
        return span.label in in_scope

    ordered = sorted(spans, key=lambda s: s.start, reverse=True)
    out = text
    masked: list[MaskedSpan] = []
    skipped: set[str] = set()
    seen: set[tuple[int, int]] = set()

    for span in ordered:
        if (span.start, span.end) in seen:
            continue
        seen.add((span.start, span.end))
        if not (0 <= span.start < span.end <= len(out)):
            continue
        if not wanted(span):
            skipped.add(span.label or "UNKNOWN")
            continue
        out = out[: span.start] + pii.mask_char * (span.end - span.start) + out[span.end :]
        masked.append(
            MaskedSpan(
                start=span.start,
                end=span.end,
                label=span.label,
                original=text[span.start : span.end],
            )
        )

    masked.reverse()  # back to document order
    return RedactionOutcome(text=out, masked=masked, skipped_labels=sorted(skipped))
