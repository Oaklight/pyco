#!/usr/bin/env python3
"""Deterministic CPU-bound workload for interpreter measurements."""

from __future__ import annotations


def main() -> None:
    total = 0
    for number in range(4_000_000):
        total += (number * number) % 7
    if total <= 0:
        raise SystemExit("unexpected result")


if __name__ == "__main__":
    main()
