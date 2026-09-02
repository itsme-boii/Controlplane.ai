import pytest

from controlplane_detectors.base import DetectorContext


@pytest.fixture
def ctx() -> DetectorContext:
    return DetectorContext(usecase_id="knowledgecopilot", jurisdiction="us")


def _raise(*_a, **_k):
    raise RuntimeError("model backend down")
