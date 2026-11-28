"""Shared command, file, and ELF utilities."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator, Mapping, Sequence


class SnugPyError(RuntimeError):
    """Base error for expected SnugPy failures."""


class CommandError(SnugPyError):
    """Raised when a subprocess exits non-zero."""

    def __init__(self, result: "CommandResult") -> None:
        self.result = result
        tail = "\n".join(result.output.splitlines()[-40:])
        message = f"command failed with exit code {result.returncode}: {shlex.join(result.cmd)}"
        if tail:
            message = f"{message}\n{tail}"
        super().__init__(message)


@dataclass(frozen=True)
class CommandResult:
    """Captured result of one subprocess."""

    cmd: tuple[str, ...]
    returncode: int
    output: str
    log_path: Path | None
    duration_s: float


def utc_now() -> str:
    """Return an RFC 3339 UTC timestamp."""

    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def log(message: str) -> None:
    """Write a progress message to standard error."""

    print(f"[snugpy] {message}", file=sys.stderr, flush=True)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Return the SHA256 digest of a file."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, data: Mapping[str, object] | Sequence[object]) -> None:
    """Write deterministic, indented JSON atomically."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def read_json(path: Path) -> dict[str, object]:
    """Read a JSON object from disk."""

    return json.loads(path.read_text(encoding="utf-8"))


def make_writable(root: Path) -> None:
    """Add owner write permission to every file and directory under root."""

    if not root.exists():
        return
    for dirpath, dirnames, filenames in os.walk(root):
        os.chmod(dirpath, os.stat(dirpath).st_mode | stat.S_IWUSR)
        for name in dirnames:
            path = Path(dirpath) / name
            if not path.is_symlink():
                os.chmod(path, os.stat(path).st_mode | stat.S_IWUSR)
        for name in filenames:
            path = Path(dirpath) / name
            if not path.is_symlink():
                os.chmod(path, os.stat(path).st_mode | stat.S_IWUSR)


def remove_tree(path: Path) -> None:
    """Remove a file tree, including read-only entries."""

    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    if not path.exists():
        return
    make_writable(path)
    shutil.rmtree(path)


def copy_tree(src: Path, dst: Path) -> None:
    """Copy a source tree and make the copy writable."""

    remove_tree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, symlinks=True)
    make_writable(dst)


def is_elf(path: Path) -> bool:
    """Return True when path starts with the ELF magic bytes."""

    try:
        with path.open("rb") as handle:
            return handle.read(4) == b"\x7fELF"
    except OSError:
        return False


def iter_unique_regular_files(
    root: Path,
    predicate: Callable[[Path], bool] | None = None,
) -> Iterator[tuple[Path, os.stat_result]]:
    """Yield regular files once, deduplicating hardlinks and skipping symlinks."""

    seen: set[tuple[int, int]] = set()
    if not root.exists():
        return
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(
            d for d in dirnames if not (Path(dirpath) / d).is_symlink()
        )
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if path.is_symlink():
                continue
            try:
                info = path.stat()
            except OSError:
                continue
            if not stat.S_ISREG(info.st_mode):
                continue
            if predicate is not None and not predicate(path):
                continue
            key = (info.st_dev, info.st_ino)
            if key in seen:
                continue
            seen.add(key)
            yield path, info


def duplicate_safe_size(paths: Sequence[Path]) -> int:
    """Sum regular file sizes once, deduplicating hardlinks and symlinks."""

    seen: set[tuple[int, int]] = set()
    total = 0
    for path in paths:
        if path.is_symlink():
            continue
        try:
            info = path.stat()
        except OSError:
            continue
        if not stat.S_ISREG(info.st_mode):
            continue
        key = (info.st_dev, info.st_ino)
        if key in seen:
            continue
        seen.add(key)
        total += info.st_size
    return total


def run_command(
    cmd: Sequence[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    log_path: Path | None = None,
    check: bool = True,
    echo: bool = False,
    timeout: float | None = None,
) -> CommandResult:
    """Run a subprocess, capture merged output, and optionally tee it to a log."""

    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    if cwd is not None:
        cwd.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    lines: list[str] = []
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handle = log_path.open("w", encoding="utf-8")
    else:
        handle = None

    try:
        if handle is not None:
            handle.write(f"$ {shlex.join(cmd)}\n")
            handle.write(f"# cwd: {cwd or Path.cwd()}\n\n")
            handle.flush()
        process = subprocess.Popen(
            list(cmd),
            cwd=str(cwd) if cwd is not None else None,
            env=full_env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            errors="replace",
        )
        assert process.stdout is not None
        try:
            for line in process.stdout:
                lines.append(line)
                if handle is not None:
                    handle.write(line)
                    handle.flush()
                if echo:
                    sys.stderr.write(line)
                    sys.stderr.flush()
            returncode = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            returncode = process.wait()
            lines.append(f"\n[snugpy] command timed out after {timeout} seconds\n")
    finally:
        if handle is not None:
            handle.close()

    result = CommandResult(
        cmd=tuple(cmd),
        returncode=returncode,
        output="".join(lines),
        log_path=log_path,
        duration_s=time.monotonic() - started,
    )
    if check and returncode != 0:
        raise CommandError(result)
    return result


def find_python(prefix: Path, version: str) -> Path:
    """Return the installed interpreter for an exact CPython version."""

    parts = version.split(".")
    short = ".".join(parts[:2])
    candidates = [
        prefix / "bin" / f"python{short}",
        prefix / "bin" / "python3",
        prefix / "bin" / "python",
        prefix / f"python{short}.exe",
        prefix / "python3.exe",
        prefix / "python.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    raise SnugPyError(f"no interpreter found under {prefix}/bin or {prefix}")


def python_runtime_env(prefix: Path) -> dict[str, str]:
    """Return an environment that prefers the built runtime and its libraries."""

    env = os.environ.copy()
    windows = os.name == "nt"
    lib_dir = str(prefix / "lib")
    bin_dir = str(prefix if windows else prefix / "bin")
    path_entries = [bin_dir]
    if windows:
        path_entries.append(str(prefix / "Scripts"))
    if env.get("PATH"):
        path_entries.append(env["PATH"])
    env["PATH"] = os.pathsep.join(path_entries)

    conda_prefix = env.get("SNUGPY_CONDA_PREFIX") or env.get("CONDA_PREFIX")
    if not windows:
        library_paths = [lib_dir]
        if conda_prefix:
            conda_lib_dir = str(Path(conda_prefix) / "lib")
            if conda_lib_dir != lib_dir:
                library_paths.append(conda_lib_dir)
        existing_library_path = env.get("LD_LIBRARY_PATH", "")
        if existing_library_path:
            library_paths.append(existing_library_path)
        joined_library_paths = ":".join(library_paths)
        env["LD_LIBRARY_PATH"] = joined_library_paths
        if sys.platform == "darwin":
            env["DYLD_LIBRARY_PATH"] = joined_library_paths
    env["PYTHONNOUSERSITE"] = "1"
    if "SSL_CERT_FILE" not in env:
        for certificate in (
            prefix / "ssl" / "cert.pem",
            prefix / "ssl" / "cacert.pem",
            Path("/etc/ssl/certs/ca-certificates.crt"),
        ):
            if certificate.exists():
                env["SSL_CERT_FILE"] = str(certificate)
                env["REQUESTS_CA_BUNDLE"] = str(certificate)
                break
    cert_dir = prefix / "ssl" / "certs"
    if not cert_dir.exists():
        cert_dir = Path("/etc/ssl/certs")
    if cert_dir.exists():
        env["SSL_CERT_DIR"] = str(cert_dir)
    return env


def git_commit(root: Path) -> str:
    """Return the current Git commit, or a stable marker when unavailable."""

    override = os.environ.get("SNUGPY_COMMIT", "").strip()
    if override:
        return override
    result = run_command(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=False,
        echo=False,
    )
    if result.returncode == 0:
        return result.output.strip()
    return "uncommitted"
