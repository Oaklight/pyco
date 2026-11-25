"""Create and verify deterministic distribution archives."""

from __future__ import annotations

import gzip
import lzma
import os
import shutil
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Callable, Sequence

from .config import BuildSpec
from .distributions import load_distributions
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


def _tree_bytes(root: Path, exclude: Callable[[str], bool] | None = None) -> int:
    total = 0
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root).as_posix()
        if exclude is not None and exclude(relative):
            continue
        total += path.stat().st_size
    return total


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


def _build_archive(
    prefix: Path,
    archive: Path,
    arc_root: str,
    *,
    exclude: Callable[[str], bool] | None = None,
) -> None:
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
            relative_text = relative.as_posix()
            if exclude is not None and exclude(relative_text):
                continue
            entries.append((f"{arc_root}/{relative_text}", path))
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


def _smoke_extracted(
    archive: Path,
    version: str,
    profile_cc: str,
    imports: tuple[str, ...] = ("ssl", "sqlite3", "ctypes"),
) -> dict[str, Any]:
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
        if imports:
            code = f"import {', '.join(imports)}; print('package-ok')"
        else:
            code = "print('package-ok')"
        result = run_command(
            [str(python), "-c", code],
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
            "imports": list(imports),
            "status": "pass",
        }


def package(spec: BuildSpec, *, only: Sequence[str] | None = None) -> dict[str, Any]:
    """Create deterministic distribution archives and smoke-test them.

    The install prefix is copied and stripped once. Every configured
    distribution is then archived from that staging tree. Passing ``only``
    limits the run to the named distributions; previously built variants are
    retained in the metadata when their archives still exist.

    Args:
        spec: Resolved build cell.
        only: Distribution names to build. None builds every configured variant.

    Returns:
        The package metadata written to ``package.json``.
    """

    paths = BuildPaths(spec)
    if not paths.prefix.exists():
        raise PackageError(f"install prefix missing: {paths.prefix}; run build first")
    distributions = load_distributions(spec.root)
    requested = (
        list(dict.fromkeys(only))
        if only
        else [variant.name for variant in distributions.variants]
    )
    selected = [distributions.get(name) for name in requested]
    configured = {variant.name for variant in distributions.variants}
    base_root = (
        f"pyco-cpython{spec.version.version}-{spec.target.name}-{spec.profile.name}"
    )
    log(f"packaging {paths.prefix}")
    prefix_bytes = _tree_bytes(paths.prefix)
    variants: dict[str, dict[str, Any]] = {}
    selected_names = {variant.name for variant in selected}
    existing = (
        read_json(paths.package_metadata) if paths.package_metadata.exists() else {}
    )
    if (
        existing.get("schema_version") == 2
        and existing.get("version") == spec.version.version
        and existing.get("target") == spec.target.name
        and existing.get("profile") == spec.profile.name
    ):
        for name, info in existing.get("variants", {}).items():
            if name in selected_names or name not in configured:
                continue
            archive_text = info.get("archive")
            if isinstance(archive_text, str) and Path(archive_text).is_file():
                variants[name] = info
    with tempfile.TemporaryDirectory(prefix="pyco-package-") as directory:
        staging = Path(directory) / base_root
        shutil.copytree(
            paths.prefix,
            staging,
            symlinks=True,
            copy_function=shutil.copy2,
        )
        strip = _strip_tree(staging)
        log(f"stripped {strip['files']} ELF files: {strip['bytes_saved']} bytes saved")
        for variant in selected:
            archive = paths.package_archive_for(variant.name)
            arc_root = f"{base_root}-{variant.name}"
            exclude = variant.matches_exclude
            installed_bytes = _tree_bytes(staging, exclude)
            _build_archive(staging, archive, arc_root, exclude=exclude)
            digest = sha256_file(archive)
            smoke = _smoke_extracted(
                archive,
                spec.version.version,
                spec.profile.cc,
                imports=variant.smoke_imports,
            )
            variants[variant.name] = {
                "description": variant.description,
                "archive": str(archive),
                "archive_format": archive.name.rsplit(".tar.", 1)[-1],
                "compression": "xz-9e" if archive.suffix == ".xz" else "gzip-9",
                "archive_bytes": archive.stat().st_size,
                "archive_sha256": digest,
                "arc_root": arc_root,
                "installed_bytes": installed_bytes,
                "exclude": list(variant.exclude),
                "smoke": smoke,
                "status": smoke["status"],
            }
            log(
                f"packaged {variant.name}: {installed_bytes} installed bytes, "
                f"{archive.stat().st_size} archive bytes"
            )
    default_name = distributions.default
    default = variants.get(default_name)
    metadata: dict[str, Any] = {
        "schema_version": 2,
        "version": spec.version.version,
        "cpython_tag": spec.version.tag,
        "target": spec.target.name,
        "profile": spec.profile.name,
        "default_distribution": default_name,
        "source_installed_bytes": prefix_bytes,
        "strip": strip,
        "variants": variants,
        "created_at": utc_now(),
    }
    if default is not None:
        metadata.update(
            {
                "archive": default["archive"],
                "archive_format": default["archive_format"],
                "compression": default["compression"],
                "archive_bytes": default["archive_bytes"],
                "archive_sha256": default["archive_sha256"],
                "arc_root": default["arc_root"],
                "installed_bytes": default["installed_bytes"],
                "status": default["status"],
                "smoke": default["smoke"],
            }
        )
    write_json(paths.package_metadata, metadata)
    if default is not None:
        log(
            f"packaged {default_name} archive {default['archive']} "
            f"({default['archive_bytes']} bytes)"
        )
    return metadata


def package_result(paths: BuildPaths) -> dict[str, Any] | None:
    """Return package metadata when it exists."""

    if not paths.package_metadata.exists():
        return None
    return read_json(paths.package_metadata)
