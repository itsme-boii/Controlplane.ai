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

    gateway_dir = Path(__file__).parent.parent / "gateway"

    cmd = [
        "uv",
        "run",
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
