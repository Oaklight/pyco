"""Create and verify deterministic distribution archives."""

from __future__ import annotations

import gzip
import lzma
import os
import shutil
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


_ET_REL = 1
_ET_EXEC = 2
_ET_DYN = 3


def _elf_type(path: Path) -> int | None:
    """Return the ELF e_type value, or None for non-ELF files."""

    try:
        with path.open("rb") as handle:
            header = handle.read(20)
    except OSError:
        return None
    if len(header) < 18 or header[:4] != b"\x7fELF":
        return None
    byteorder = "little" if header[5] == 1 else "big"
    return int.from_bytes(header[16:18], byteorder)


def _is_archive(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(8) == b"!<arch>\n"
    except OSError:
        return False


def _tree_bytes(root: Path) -> int:
    return sum(
        path.stat().st_size
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    )


def _strip_tree(root: Path) -> dict[str, Any]:
    """Strip executable and shared ELF files in a staged install tree."""

    strip = shutil.which("strip")
    if strip is None:
        raise PackageError("strip was not found on PATH")
    before = 0
    after = 0
    binaries = 0
    objects = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(dirnames)
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if path.is_symlink():
                continue
            kind = _elf_type(path)
            if kind in {_ET_EXEC, _ET_DYN}:
                options = ["--strip-unneeded"]
                binaries += 1
            elif kind == _ET_REL or _is_archive(path):
                options = ["--strip-debug"]
                objects += 1
            else:
                continue
            size_before = path.stat().st_size
            run_command([strip, *options, str(path)])
            size_after = path.stat().st_size
            before += size_before
            after += size_after
    count = binaries + objects
    if count == 0:
        raise PackageError("no ELF files or static archives found to strip")
    return {
        "files": count,
        "binaries": binaries,
        "objects_and_archives": objects,
        "bytes_before": before,
        "bytes_after": after,
        "bytes_saved": before - after,
    }


def _write_tar(compressed: Any, entries: list[tuple[str, Path]], epoch: int) -> None:
    with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for arcname, path in entries:
            _add_entry(tar, path, arcname, epoch)


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
        if archive.suffix == ".xz":
            with lzma.LZMAFile(
                raw, mode="wb", preset=9 | lzma.PRESET_EXTREME
            ) as compressed:
                _write_tar(compressed, entries, epoch)
        elif archive.suffix == ".gz":
            with gzip.GzipFile(
                filename="", mode="wb", fileobj=raw, mtime=0
            ) as compressed:
                _write_tar(compressed, entries, epoch)
        else:
            raise PackageError(f"unsupported archive suffix: {archive.suffix}")
    os.replace(temporary, archive)


def _smoke_extracted(archive: Path, version: str, profile_cc: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="pyco-package-") as directory:
        extract_root = Path(directory)
        with tarfile.open(archive, "r:*") as handle:
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
    prefix_bytes = _tree_bytes(paths.prefix)
    with tempfile.TemporaryDirectory(prefix="pyco-package-") as directory:
        staging = Path(directory) / arc_root
        shutil.copytree(
            paths.prefix,
            staging,
            symlinks=True,
            copy_function=shutil.copy2,
        )
        strip = _strip_tree(staging)
        installed_bytes = _tree_bytes(staging)
        log(f"stripped {strip['files']} ELF files: {strip['bytes_saved']} bytes saved")
        _build_archive(staging, archive, arc_root)
    digest = sha256_file(archive)
    smoke = _smoke_extracted(archive, spec.version.version, spec.profile.cc)
    compression = "xz-9e" if archive.suffix == ".xz" else "gzip-9"
    metadata: dict[str, Any] = {
        "schema_version": 1,
        "version": spec.version.version,
        "cpython_tag": spec.version.tag,
        "target": spec.target.name,
        "profile": spec.profile.name,
        "archive": str(archive),
        "archive_format": archive.name.rsplit(".tar.", 1)[-1],
        "compression": compression,
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": digest,
        "arc_root": arc_root,
        "source_installed_bytes": prefix_bytes,
        "installed_bytes": installed_bytes,
        "strip": strip,
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
