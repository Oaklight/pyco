"""Create and verify deterministic distribution archives."""

from __future__ import annotations

import gzip
import os
import tarfile
import tempfile
from pathlib import Path
from typing import Any

from .config import BuildSpec
from .paths import BuildPaths
from .util import (
    PycoError,
    find_python,
    log,
    python_runtime_env,
    read_json,
    run_command,
    sha256_file,
    utc_now,
    write_json,
)


class PackageError(PycoError):
    """Raised when packaging or extraction validation fails."""


def _add_entry(tar: tarfile.TarFile, path: Path, arcname: str, epoch: int) -> None:
    info = tar.gettarinfo(str(path), arcname=arcname)
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = epoch
    if info.isfile():
        with path.open("rb") as handle:
            tar.addfile(info, handle)
    else:
        tar.addfile(info)


def _build_archive(prefix: Path, archive: Path, arc_root: str) -> None:
    archive.parent.mkdir(parents=True, exist_ok=True)
    temporary = archive.with_suffix(archive.suffix + ".tmp")
    if temporary.exists():
        temporary.unlink()
    epoch = int(os.environ.get("SOURCE_DATE_EPOCH", "0"))
    entries: list[tuple[str, Path]] = [(arc_root, prefix)]
    for dirpath, dirnames, filenames in os.walk(prefix):
        dirnames[:] = sorted(dirnames)
        for name in sorted(filenames):
            path = Path(dirpath) / name
            relative = path.relative_to(prefix)
            entries.append((f"{arc_root}/{relative.as_posix()}", path))
    entries.sort(key=lambda item: item[0])

    with temporary.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(
                fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT
            ) as tar:
                for arcname, path in entries:
                    _add_entry(tar, path, arcname, epoch)
    os.replace(temporary, archive)


def _smoke_extracted(archive: Path, version: str, profile_cc: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="pyco-package-") as directory:
        extract_root = Path(directory)
        with tarfile.open(archive, "r:gz") as handle:
            try:
                handle.extractall(extract_root, filter="data")
            except TypeError:
                handle.extractall(extract_root)
        entries = list(extract_root.iterdir())
        if len(entries) != 1 or not entries[0].is_dir():
            raise PackageError("archive does not contain exactly one root directory")
        runtime_root = entries[0]
        python = find_python(runtime_root, version)
        result = run_command(
            [str(python), "-c", "import ssl, sqlite3, ctypes; print('package-ok')"],
            env=python_runtime_env(runtime_root),
            check=False,
        )
        if result.returncode != 0:
            raise PackageError(
                f"extracted package smoke test failed: {result.output.strip()}"
            )
        return {
            "runtime_root": str(runtime_root),
            "python": str(python),
            "status": "pass",
        }


def package(spec: BuildSpec) -> dict[str, Any]:
    """Create a deterministic tarball and test it from a clean extraction."""

    paths = BuildPaths(spec)
    if not paths.prefix.exists():
        raise PackageError(f"install prefix missing: {paths.prefix}; run build first")
    archive = paths.package_archive
    arc_root = (
        f"pyco-cpython{spec.version.version}-{spec.target.name}-{spec.profile.name}"
    )
    log(f"packaging {paths.prefix}")
    _build_archive(paths.prefix, archive, arc_root)
    digest = sha256_file(archive)
    smoke = _smoke_extracted(archive, spec.version.version, spec.profile.cc)
    metadata: dict[str, Any] = {
        "schema_version": 1,
        "version": spec.version.version,
        "cpython_tag": spec.version.tag,
        "target": spec.target.name,
        "profile": spec.profile.name,
        "archive": str(archive),
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": digest,
        "arc_root": arc_root,
        "status": smoke["status"],
        "smoke": smoke,
        "created_at": utc_now(),
    }
    write_json(paths.package_metadata, metadata)
    log(f"packaged {archive} ({archive.stat().st_size} bytes)")
    return metadata


def package_result(paths: BuildPaths) -> dict[str, Any] | None:
    """Return package metadata when it exists."""

    if not paths.package_metadata.exists():
        return None
    return read_json(paths.package_metadata)
