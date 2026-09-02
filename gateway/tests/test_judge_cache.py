"""Tests for the judge cache."""

import pytest
from controlplane_detectors import Category, DetectionResult, Detector, DetectorContext, Severity

from controlplane_gateway.judge_cache import CachedJudgeDetector


class FakeDetector(Detector):
    name = "judge.llm_rubric"
    check = "judge"

    def __init__(self):
        self.calls = 0

    async def analyze(self, text, context):
        self.calls += 1
        return DetectionResult(
            detector=self.name,
            ok=True,
            categories=[Category.POLICY],
            severity=Severity.HIGH,
            confidence=0.9,
        )


class FakeRedis:
    def __init__(self):
        self.store = {}
        self.broken = False

    async def get(self, key):
        if self.broken:
            raise Exception("redis down")
        return self.store.get(key)

    async def setex(self, key, ttl, val):
        if self.broken:
            raise Exception("redis down")
        self.store[key] = val


@pytest.fixture
def fake_inner():
    return FakeDetector()


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.fixture
def cache_detector(fake_inner, fake_redis):
    return CachedJudgeDetector(fake_inner, fake_redis, "v1", 60)


@pytest.mark.asyncio
async def test_cache_miss_calls_inner_and_stores(cache_detector, fake_inner, fake_redis):
    context = DetectorContext(prompt="test")
    res = await cache_detector.analyze("response", context)
    assert fake_inner.calls == 1
    assert res.severity == Severity.HIGH
    assert len(fake_redis.store) == 1


@pytest.mark.asyncio
async def test_cache_hit_skips_inner(cache_detector, fake_inner, fake_redis):
    context = DetectorContext(prompt="test")

    # Pre-populate cache
    await cache_detector.analyze("response", context)
    assert fake_inner.calls == 1

    # Second call should hit
    res2 = await cache_detector.analyze("response", context)
    assert fake_inner.calls == 1  # unchanged
    assert res2.severity == Severity.HIGH


@pytest.mark.asyncio
async def test_broken_redis_falls_back_to_inner(cache_detector, fake_inner, fake_redis):
    fake_redis.broken = True
    context = DetectorContext(prompt="test")

    res = await cache_detector.analyze("response", context)
    assert fake_inner.calls == 1
    assert res.severity == Severity.HIGH
    # Should not crash, just returns real result
