#!/usr/bin/env python3
"""Runtime smoke checks for a built SnugPy interpreter."""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import json
import os
import sqlite3
import ssl
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

REQUIRED_MODULES = (
    "asyncio",
    "bz2",
    "concurrent.futures",
    "curses",
    "ctypes",
    "email",
    "ensurepip",
    "http",
    "lzma",
    "multiprocessing",
    "readline",
    "socket",
    "sqlite3",
    "ssl",
    "subprocess",
    "tkinter",
    "unittest",
    "urllib",
    "venv",
    "xml",
)

WINDOWS_UNSUPPORTED_MODULES = {"curses", "readline", "tkinter"}
DARWIN_OPTIONAL_MODULES = {"tkinter"}
if os.name == "nt":
    REQUIRED_MODULES = tuple(
        name for name in REQUIRED_MODULES if name not in WINDOWS_UNSUPPORTED_MODULES
    )
elif sys.platform == "darwin":
    REQUIRED_MODULES = tuple(
        name for name in REQUIRED_MODULES if name not in DARWIN_OPTIONAL_MODULES
    )


def check_imports() -> None:
    """Import the stdlib modules required by the compatibility plan."""

    import importlib

    failed: list[str] = []
    for name in REQUIRED_MODULES:
        try:
            importlib.import_module(name)
        except Exception as error:  # noqa: BLE001 - report the module and error
            failed.append(f"{name}: {type(error).__name__}: {error}")
    if failed:
        raise RuntimeError("import failures:\n" + "\n".join(failed))


def check_sqlite() -> None:
    """Run an in-memory SQLite query."""

    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE TABLE items (value INTEGER)")
        connection.executemany("INSERT INTO items VALUES (?)", [(1,), (2,), (3,)])
        total = connection.execute("SELECT SUM(value) FROM items").fetchone()[0]
        if total != 6:
            raise RuntimeError(f"sqlite result mismatch: {total}")
    finally:
        connection.close()


def check_ctypes() -> None:
    """Load a native library through ctypes."""

    library = ctypes.pythonapi
    if not hasattr(library, "Py_GetVersion"):
        raise RuntimeError(
            "ctypes could not resolve symbols from the running interpreter"
        )


def check_subprocess() -> None:
    """Run a child interpreter and read its output."""

    result = subprocess.run(
        [sys.executable, "-c", "print('snugpy-child-ok')"],
        check=True,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip() != "snugpy-child-ok":
        raise RuntimeError(f"subprocess output mismatch: {result.stdout!r}")


def check_threading() -> None:
    """Exercise threads and a lock."""

    lock = threading.Lock()
    total = 0

    def worker() -> None:
        nonlocal total
        for _ in range(1000):
            with lock:
                total += 1

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    if total != 4000:
        raise RuntimeError(f"thread total mismatch: {total}")


def check_asyncio() -> None:
    """Run a small event loop."""

    async def gather_values() -> list[int]:
        async def value(number: int) -> int:
            await asyncio.sleep(0)
            return number

        return await asyncio.gather(*(value(number) for number in range(5)))

    result = asyncio.run(gather_values())
    if result != [0, 1, 2, 3, 4]:
        raise RuntimeError(f"asyncio result mismatch: {result}")


def check_ssl() -> None:
    """Verify the default TLS context and OpenSSL bindings load."""

    context = ssl.create_default_context()
    if not context.verify_mode == ssl.CERT_REQUIRED:
        raise RuntimeError(
            "default TLS context does not require certificate verification"
        )
    if not ssl.OPENSSL_VERSION:
        raise RuntimeError("OpenSSL version is empty")
    if os.name != "nt":
        paths = ssl.get_default_verify_paths()
        if not any((paths.cafile, paths.capath)):
            raise RuntimeError("no default certificate verification path is configured")


def check_filesystem() -> None:
    """Exercise filesystem writes, reads, and temp files."""

    with tempfile.TemporaryDirectory(prefix="snugpy-smoke-") as directory:
        path = Path(directory) / "payload.txt"
        path.write_text("snugpy", encoding="utf-8")
        if path.read_text(encoding="utf-8") != "snugpy":
            raise RuntimeError("filesystem round trip failed")
        os.replace(path, Path(directory) / "moved.txt")
        if not (Path(directory) / "moved.txt").exists():
            raise RuntimeError("os.replace failed")


def check_dbm() -> None:
    """Exercise the ndbm-backed dbm module."""

    import dbm.ndbm

    with tempfile.TemporaryDirectory(prefix="snugpy-dbm-") as directory:
        path = Path(directory) / "records"
        with dbm.ndbm.open(str(path), "c") as database:
            database[b"key"] = b"value"
        with dbm.ndbm.open(str(path), "r") as database:
            if database[b"key"] != b"value":
                raise RuntimeError("dbm round trip failed")


CHECKS = [
    ("imports", check_imports),
    ("sqlite", check_sqlite),
    ("ctypes", check_ctypes),
    ("subprocess", check_subprocess),
    ("threading", check_threading),
    ("asyncio", check_asyncio),
    ("ssl", check_ssl),
    ("filesystem", check_filesystem),
]
if os.name != "nt" and sys.platform != "darwin":
    CHECKS.append(("dbm", check_dbm))
CHECKS = tuple(CHECKS)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json", action="store_true", help="write a machine-readable result"
    )
    args = parser.parse_args()

    results: dict[str, str] = {}
    failures: list[str] = []
    for name, check in CHECKS:
        try:
            check()
        except Exception as error:  # noqa: BLE001 - aggregate all smoke failures
            results[name] = f"fail: {type(error).__name__}: {error}"
            failures.append(name)
        else:
            results[name] = "pass"

    payload = {
        "python": sys.executable,
        "version": sys.version,
        "results": results,
        "failures": failures,
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for name, status in results.items():
            print(f"{name}: {status}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
