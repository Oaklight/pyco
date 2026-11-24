"""Fetch and verify immutable upstream source trees."""

from __future__ import annotations

import os
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .config import Config, VersionPin
from .paths import BuildPaths
from .util import (
    PycoError,
    log,
    read_json,
    remove_tree,
    run_command,
    sha256_file,
    utc_now,
    write_json,
)


class SourceError(PycoError):
    """Raised when source acquisition or verification fails."""


def _make_readonly(root: Path) -> None:
    """Remove write permission from every entry under root."""

    for dirpath, dirnames, filenames in os.walk(root):
        for name in [*dirnames, *filenames]:
            path = Path(dirpath) / name
            if path.is_symlink():
                continue
            try:
                mode = path.stat().st_mode
                path.chmod(mode & ~0o222)
            except OSError:
                pass
        try:
            mode = Path(dirpath).stat().st_mode
            Path(dirpath).chmod(mode & ~0o222)
        except OSError:
            pass


def _download(url: str, destination: Path, expected_sha256: str, force: bool) -> None:
    """Download a URL once, checking the SHA256 before publishing it."""

    if destination.exists():
        actual = sha256_file(destination)
        if actual == expected_sha256:
            log(f"using cached source archive {destination}")
            return
        if not force:
            raise SourceError(
                f"cached archive checksum mismatch: {destination} "
                f"(expected {expected_sha256}, got {actual}); rerun with --force"
            )
        destination.unlink()

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    if temporary.exists():
        temporary.unlink()
    log(f"downloading {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "pyco-build/0.1"})
    try:
        with (
            urllib.request.urlopen(request, timeout=120) as response,
            temporary.open("wb") as handle,
        ):
            while chunk := response.read(1024 * 1024):
                handle.write(chunk)
    except (urllib.error.URLError, OSError) as error:
        if temporary.exists():
            temporary.unlink()
        raise SourceError(f"download failed for {url}: {error}") from error

    actual = sha256_file(temporary)
    if actual != expected_sha256:
        temporary.unlink()
        raise SourceError(
            f"downloaded archive checksum mismatch for {url}: "
            f"expected {expected_sha256}, got {actual}"
        )
    os.replace(temporary, destination)


def _safe_extract(archive: Path, destination: Path) -> None:
    """Extract a tar archive after rejecting absolute and parent paths."""

    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:*") as handle:
        members = handle.getmembers()
        for member in members:
            member_path = Path(member.name)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise SourceError(f"unsafe path in archive: {member.name}")
        try:
            handle.extractall(destination, filter="data")
        except TypeError:
            handle.extractall(destination)


def _source_state_path(paths: BuildPaths) -> Path:
    return paths.source_state


def _write_source_state(paths: BuildPaths, archive_sha256: str) -> None:
    data = {
        "url": paths.spec.version.url,
        "sha256": archive_sha256,
        "tag": paths.spec.version.tag,
        "version": paths.spec.version.version,
        "git_commit": paths.spec.version.git_commit,
        "source_dir": str(paths.spec.version.source_dir),
        "extracted_at": utc_now(),
    }
    write_json(_source_state_path(paths), data)


def _read_source_state(paths: BuildPaths) -> dict[str, Any]:
    state_path = _source_state_path(paths)
    if not state_path.exists():
        raise SourceError(
            f"source state missing for {paths.source}; rerun scripts/fetch.sh {paths.version}"
        )
    return read_json(state_path)


def verify_source(spec: Any) -> dict[str, Any]:
    """Verify that a pristine source tree matches its pin and state marker."""

    paths = BuildPaths(spec)
    if not paths.source.is_dir():
        raise SourceError(
            f"source tree missing: {paths.source}; run scripts/fetch.sh {paths.version}"
        )
    state = _read_source_state(paths)
    expected = {
        "url": spec.version.url,
        "sha256": spec.version.sha256,
        "tag": spec.version.tag,
        "version": spec.version.version,
        "git_commit": spec.version.git_commit,
        "source_dir": str(spec.version.source_dir),
    }
    for key, value in expected.items():
        if state.get(key) != value:
            raise SourceError(
                f"source state mismatch for {key}: expected {value!r}, got {state.get(key)!r}; "
                f"rerun fetch with --force"
            )
    if not (paths.source / "configure").is_file():
        raise SourceError(
            f"source tree is incomplete: {paths.source / 'configure'} is missing"
        )
    return state


def fetch_version(spec: Any, force: bool = False) -> BuildPaths:
    """Fetch, verify, and immutably extract one pinned CPython release."""

    paths = BuildPaths(spec)
    pin: VersionPin = spec.version
    source_state = _source_state_path(paths)

    if paths.source.exists():
        if source_state.exists() and not force:
            verify_source(spec)
            log(f"source already verified: {paths.source}")
            return paths
        if not force:
            raise SourceError(
                f"source directory exists without a matching state marker: {paths.source}; "
                f"rerun with --force to replace it"
            )
        remove_tree(paths.source)
        if source_state.exists():
            source_state.unlink()

    _download(pin.url, paths.archive, pin.sha256, force=force)

    with tempfile.TemporaryDirectory(
        prefix="pyco-source-", dir=str(paths.root / "sources")
    ) as tmp_name:
        tmp = Path(tmp_name)
        _safe_extract(paths.archive, tmp)
        entries = list(tmp.iterdir())
        if len(entries) != 1 or not entries[0].is_dir():
            raise SourceError(f"unexpected source archive layout in {paths.archive}")
        extracted = entries[0]
        expected_name = f"Python-{pin.version}"
        if extracted.name != expected_name:
            raise SourceError(
                f"source archive root is {extracted.name!r}, expected {expected_name!r}"
            )
        paths.source.parent.mkdir(parents=True, exist_ok=True)
        os.replace(extracted, paths.source)

    _write_source_state(paths, pin.sha256)
    _make_readonly(paths.source)
    log(f"extracted verified source: {paths.source}")
    return paths


def fetch_zerodep(config: Config, force: bool = False) -> Path:
    """Clone the pinned zerodep commit into an immutable source tree."""

    pin = config.zerodep
    destination = config.root / "sources" / f"zerodep-{pin.tag}"
    state_path = config.root / "sources" / ".state" / f"zerodep-{pin.tag}.json"

    if destination.exists():
        if not state_path.exists():
            if not force:
                raise SourceError(
                    f"zerodep source exists without a state marker: {destination}; "
                    f"rerun with --force to replace it"
                )
            remove_tree(destination)
        else:
            state = read_json(state_path)
            if state.get("commit") != pin.commit:
                if not force:
                    raise SourceError(
                        f"zerodep state mismatch: expected {pin.commit}, "
                        f"got {state.get('commit')}; rerun with --force"
                    )
                remove_tree(destination)
                state_path.unlink()
            else:
                result = run_command(
                    ["git", "-C", str(destination), "rev-parse", "HEAD"],
                    check=False,
                )
                if result.returncode != 0 or result.output.strip() != pin.commit:
                    raise SourceError(
                        f"zerodep checkout is dirty or has the wrong commit: {destination}"
                    )
                return destination

    temporary = Path(
        tempfile.mkdtemp(prefix="pyco-zerodep-", dir=str(config.root / "sources"))
    )
    remove_tree(temporary)
    log(f"cloning zerodep {pin.tag} ({pin.commit})")
    result = run_command(
        [
            "git",
            "clone",
            "--quiet",
            "--depth",
            "1",
            "--branch",
            pin.tag,
            pin.repo,
            str(temporary),
        ],
        check=False,
    )
    if result.returncode != 0:
        remove_tree(temporary)
        raise SourceError(f"zerodep clone failed: {result.output.strip()}")
    revision = run_command(
        ["git", "-C", str(temporary), "rev-parse", "HEAD"], check=False
    )
    if revision.returncode != 0 or revision.output.strip() != pin.commit:
        remove_tree(temporary)
        raise SourceError(
            f"zerodep commit mismatch: expected {pin.commit}, got {revision.output.strip()}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(temporary, destination)
    write_json(
        state_path,
        {
            "repo": pin.repo,
            "tag": pin.tag,
            "commit": pin.commit,
            "requires_python": pin.requires_python,
            "fetched_at": utc_now(),
        },
    )
    _make_readonly(destination)
    log(f"fetched zerodep: {destination}")
    return destination


def force_clean_source(spec: Any) -> None:
    """Delete a generated source tree for an explicit refetch."""

    paths = BuildPaths(spec)
    if paths.source.exists():
        remove_tree(paths.source)
    if _source_state_path(paths).exists():
        _source_state_path(paths).unlink()
