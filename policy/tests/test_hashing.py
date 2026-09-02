from controlplane_policy.hashing import canonical_json, content_hash, version_label


def test_canonical_json_is_key_order_independent():
    a = {"b": 1, "a": {"y": 2, "x": 3}}
    b = {"a": {"x": 3, "y": 2}, "b": 1}
    assert canonical_json(a) == canonical_json(b)


def test_content_hash_is_deterministic_and_sensitive():
    base = {"latency_budget_ms": 1500, "checks": {"pii": {"enabled": True}}}
    assert content_hash(base) == content_hash(dict(base))

    changed = {"latency_budget_ms": 400, "checks": {"pii": {"enabled": True}}}
    assert content_hash(base) != content_hash(changed)


def test_version_label_shape():
    label = version_label("supportassist+eu", {"x": 1})
    name, digest = label.split(":")
    assert name == "supportassist+eu"
    assert len(digest) == 12
