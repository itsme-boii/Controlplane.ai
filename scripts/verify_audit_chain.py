#!/usr/bin/env python3
import argparse
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--table", required=True, choices=["audit_records", "action_records", "retention_log"]
    )
    args = parser.parse_args()

    root = Path(__file__).parent.parent
    gateway_dir = root / "gateway"

    cmd = [
        "uv",
        "run",
        # controlplane_gateway.config's `env_file=".env"` resolves relative
        # to CWD (gateway_dir below) — there's no gateway/.env, so without
        # this the real .env at the repo root is silently never read and
        # DATABASE_URL falls back to the hardcoded local-postgres default.
        "--env-file",
        str(root / ".env"),
        "python",
        "-m",
        "controlplane_gateway.audit.verify",
        "--table",
        args.table,
    ]

    result = subprocess.run(cmd, cwd=gateway_dir)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
