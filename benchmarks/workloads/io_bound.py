#!/usr/bin/env python3
"""Deterministic I/O-bound workload for interpreter measurements."""

from __future__ import annotations

import tempfile
from pathlib import Path


def main() -> None:
    payload = b"snugpy" * 262_144
    with tempfile.TemporaryDirectory(prefix="snugpy-bench-") as directory:
        path = Path(directory) / "payload.bin"
        for _ in range(8):
            path.write_bytes(payload)
            if path.read_bytes() != payload:
                raise SystemExit("I/O round trip failed")


if __name__ == "__main__":
    main()
