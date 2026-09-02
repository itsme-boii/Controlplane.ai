from pathlib import Path

import pytest

from controlplane_policy import PolicyEngine, PolicyRepo

# Tests run against the *real* policy packs shipped in the repo, not fixtures —
# a broken pack should fail CI.
POLICIES_DIR = Path(__file__).resolve().parents[2] / "policies"


@pytest.fixture(scope="session")
def engine() -> PolicyEngine:
    return PolicyEngine(PolicyRepo.from_dir(POLICIES_DIR))
