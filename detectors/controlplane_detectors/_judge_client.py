"""Independent HTTP client for the AI-as-judge detector.

The dependency direction in this repo is gateway -> detectors, never the reverse.
The judge needs its own small, independent HTTP client so controlplane-detectors
stays usable standalone.
"""

import os

# Use the cheapest/smallest model available for the judge if possible.
# Defaults to the same model as the main gateway if not overridden.
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b"))
JUDGE_API_KEY = os.environ.get("GROQ_API_KEY", "")
JUDGE_BASE_URL = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
JUDGE_TIMEOUT_S = float(os.environ.get("JUDGE_TIMEOUT_S", "20"))
