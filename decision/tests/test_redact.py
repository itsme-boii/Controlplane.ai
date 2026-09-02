from __future__ import annotations

from controlplane_detectors import Span
from controlplane_policy import PiiHandling

from controlplane_decision.redact import redact_spans


def _span(text: str, sub: str, label: str) -> Span:
    start = text.index(sub)
    return Span(start=start, end=start + len(sub), text=sub, label=label)


def test_masks_in_scope_spans_in_place():
    text = "Email jane@acme.com or call 555-0100."
    spans = [_span(text, "jane@acme.com", "EMAIL_ADDRESS"), _span(text, "555-0100", "PHONE_NUMBER")]
    out = redact_spans(text, spans, PiiHandling(entities=["EMAIL_ADDRESS", "PHONE_NUMBER"]))
    assert "jane@acme.com" not in out.text
    assert "555-0100" not in out.text
    assert out.text.startswith("Email ")
    assert out.text.endswith(".")
    assert len(out.text) == len(text)  # same length — mask is char-for-char
    assert {m.label for m in out.masked} == {"EMAIL_ADDRESS", "PHONE_NUMBER"}


def test_out_of_scope_entity_is_skipped_and_surfaced():
    text = "Contact jane@acme.com in Berlin."
    spans = [_span(text, "jane@acme.com", "EMAIL_ADDRESS"), _span(text, "Berlin", "LOCATION")]
    out = redact_spans(text, spans, PiiHandling(entities=["EMAIL_ADDRESS"]))
    assert "jane@acme.com" not in out.text
    assert "Berlin" in out.text
    assert out.skipped_labels == ["LOCATION"]


def test_empty_entity_list_masks_every_flagged_span():
    text = "SSN 219-09-9999 here."
    out = redact_spans(text, [_span(text, "219-09-9999", "US_SSN")], PiiHandling(entities=[]))
    assert "219-09-9999" not in out.text
    assert out.changed


def test_nothing_to_mask_reports_no_change():
    out = redact_spans("all clear", [], PiiHandling())
    assert out.text == "all clear"
    assert out.changed is False


def test_overlapping_duplicate_spans_are_applied_once():
    text = "id 219-09-9999."
    s = _span(text, "219-09-9999", "US_SSN")
    out = redact_spans(text, [s, s], PiiHandling(entities=["US_SSN"]))
    assert out.text == "id " + "•" * 11 + "."
    assert len(out.masked) == 1
