"""Isolated CPython builds for one version, target, and profile."""

from __future__ import annotations

import os
import platform
import re
import shlex
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .config import BuildSpec
from .paths import BuildPaths
from .source import verify_source
from .util import (
    SnugPyError,
    copy_tree,
    find_python,
    is_elf,
    log,
    python_runtime_env,
    remove_tree,
    run_command,
    utc_now,
    write_json,
)

MAKEFILE_FLAG_RE = re.compile(r"^([A-Za-z0-9_]+)\s*=\s*(.*)$")
DRY_RUN_ENV_KEYS = (
    "CC",
    "CXX",
    "CFLAGS",
    "CPPFLAGS",
    "CXXFLAGS",
    "LDFLAGS",
    "PKG_CONFIG_PATH",
    "LIBRARY_PATH",
    "LD_LIBRARY_PATH",
)


class BuildError(SnugPyError):
    """Raised when a build cannot be completed."""


@dataclass(frozen=True)
class BuildResult:
    """Result of one build invocation."""

    paths: BuildPaths
    status: str
    metadata: dict[str, Any]


def _flags_in_makefile(makefile: Path) -> dict[str, str]:
    """Collect compiler and linker variables from a generated Makefile."""

    if not makefile.exists():
        return {}
    interesting = ("CFLAGS", "LDFLAGS", "OPT")
    values: dict[str, str] = {}
    for line in makefile.read_text(encoding="utf-8", errors="replace").splitlines():
        match = MAKEFILE_FLAG_RE.match(line)
        if not match:
            continue
        name, value = match.groups()
        if any(token in name for token in interesting):
            values[name] = value.strip()
    return values


def _flag_tokens_applied(flags: str, effective: dict[str, str]) -> bool:
    """Return True when every requested flag appears in the generated Makefile."""

    tokens = flags.split()
    if not tokens:
        return True
    combined = " ".join(effective.values())
    return all(token in combined for token in tokens)


def _first_line(cmd: list[str]) -> str:
    result = run_command(cmd, check=False)
    text = result.output.strip()
    return text.splitlines()[0] if text else ""


def _host_metadata() -> dict[str, Any]:
    os_release: dict[str, str] = {}
    os_release_path = Path("/etc/os-release")
    if os_release_path.exists():
        for line in os_release_path.read_text(
            encoding="utf-8", errors="replace"
        ).splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                os_release[key] = value.strip().strip('"')
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "python": platform.python_version(),
        "os_release": os_release,
        "kernel": platform.release(),
    }


def _toolchain_metadata(spec: BuildSpec) -> dict[str, str]:
    return {
        "cc": _first_line([spec.profile.cc, "--version"]),
        "cxx": _first_line([spec.profile.cxx, "--version"]),
        "ld": _first_line(["ld", "--version"]),
        "make": _first_line(["make", "--version"]),
        "python3": _first_line(["python3", "--version"]),
        "libc": _first_line(["ldd", "--version"]),
        "patch": _first_line(["patch", "--version"]),
    }


def _apply_patches(spec: BuildSpec, work_src: Path, logs_dir: Path) -> list[str]:
    """Apply common patches first, then version-specific patches."""

    patch_files: list[Path] = []
    for directory in (
        spec.root / "patches" / "common",
        spec.root / "patches" / spec.version.key,
    ):
        if directory.is_dir():
            patch_files.extend(sorted(directory.glob("*.patch")))

    applied: list[str] = []
    for index, patch_file in enumerate(patch_files, start=1):
        log(f"applying patch {patch_file.relative_to(spec.root)}")
        result = run_command(
            ["patch", "--batch", "--forward", "-p1", "-i", str(patch_file)],
            cwd=work_src,
            log_path=logs_dir / f"patch-{index:02d}.log",
            check=False,
        )
        if result.returncode != 0:
            raise BuildError(
                f"patch failed: {patch_file.relative_to(spec.root)}; see {result.log_path}"
            )
        applied.append(str(patch_file.relative_to(spec.root)))
    return applied


def _set_install_rpath(paths: BuildPaths, python: Path) -> str:
    """Make the installed interpreter find libpython relative to its prefix."""

    rpath = "$ORIGIN/../lib"
    target = python.resolve()
    if not is_elf(target):
        raise BuildError(f"installed interpreter is not an ELF file: {target}")
    patchelf = shutil.which("patchelf")
    if not patchelf:
        raise BuildError("patchelf was not found on PATH")
    result = run_command(
        [patchelf, "--set-rpath", rpath, str(target)],
        log_path=paths.logs_dir / "rpath.log",
        check=False,
    )
    if result.returncode != 0:
        raise BuildError(f"patchelf failed; see {result.log_path}")
    return rpath


def _config_probe(python: Path, prefix: Path) -> dict[str, Any]:
    """Read effective CPython build configuration from the installed runtime."""

    code = (
        "import json, sysconfig; "
        "print(json.dumps({"
        "'config_args': sysconfig.get_config_var('CONFIG_ARGS') or '', "
        "'Py_ENABLE_SHARED': sysconfig.get_config_var('Py_ENABLE_SHARED'), "
        "'CFLAGS': sysconfig.get_config_var('CFLAGS') or '', "
        "'LDFLAGS': sysconfig.get_config_var('LDFLAGS') or ''"
        "}))"
    )
    result = run_command(
        [str(python), "-c", code], env=python_runtime_env(prefix), check=False
    )
    if result.returncode != 0:
        raise BuildError(f"configuration probe failed: {result.output.strip()}")
    import json

    data = json.loads(result.output)
    if not isinstance(data, dict):
        raise BuildError("configuration probe returned a non-object")
    return data


def _verify_installed_build(
    spec: BuildSpec, paths: BuildPaths, effective_flags: dict[str, str]
) -> dict[str, Any]:
    """Check that the installed runtime used the requested profile."""

    if not _flag_tokens_applied(spec.profile.cflags, effective_flags):
        raise BuildError(
            "profile CFLAGS were not found in the generated Makefile; "
            f"requested {spec.profile.cflags!r}, generated values {effective_flags!r}"
        )
    if not _flag_tokens_applied(spec.profile.ldflags, effective_flags):
        raise BuildError(
            "profile LDFLAGS were not found in the generated Makefile; "
            f"requested {spec.profile.ldflags!r}, generated values {effective_flags!r}"
        )

    python = find_python(paths.prefix, spec.version.version)
    config = _config_probe(python, paths.prefix)
    shared = bool(int(config.get("Py_ENABLE_SHARED") or 0))
    wants_shared = "--disable-shared" not in spec.profile.configure
    if shared != wants_shared:
        raise BuildError(
            f"shared-library state mismatch: Py_ENABLE_SHARED={int(shared)}, "
            f"requested shared={wants_shared}"
        )
    return {"python": str(python), "config": config}


def _save_metadata(
    spec: BuildSpec,
    paths: BuildPaths,
    *,
    status: str,
    started_at: str,
    patches: list[str],
    effective_flags: dict[str, str],
    installed: dict[str, Any],
    jobs: int,
    error: str | None = None,
) -> dict[str, Any]:
    finished_at = utc_now()
    metadata: dict[str, Any] = {
        "schema_version": 1,
        "status": status,
        "version": spec.version.version,
        "cpython_tag": spec.version.tag,
        "cpython_version": spec.version.version,
        "cpython_commit": spec.version.git_commit,
        "cpython_sha256": spec.version.sha256,
        "cpython_url": spec.version.url,
        "target": spec.target.name,
        "profile": spec.profile.name,
        "profile_description": spec.profile.description,
        "profile_spec": asdict(spec.profile),
        "experimental": spec.profile.experimental,
        "configure_flags": list(spec.profile.configure),
        "cflags": spec.profile.cflags,
        "cppflags": spec.profile.cppflags,
        "cxxflags": spec.profile.cxxflags,
        "ldflags": spec.profile.ldflags,
        "environment": spec.profile.environment(),
        "jobs": jobs,
        "patches": patches,
        "effective_flags": effective_flags,
        "installed": installed,
        "toolchain": _toolchain_metadata(spec),
        "host": _host_metadata(),
        "paths": {
            "source": str(paths.source),
            "work_root": str(paths.work_root),
            "work_src": str(paths.work_src),
            "build_dir": str(paths.build_dir),
            "prefix": str(paths.prefix),
            "logs_dir": str(paths.logs_dir),
        },
        "started_at": started_at,
        "finished_at": finished_at,
        "error": error,
    }
    write_json(paths.build_metadata, metadata)
    return metadata


def build(
    spec: BuildSpec, jobs: int | None = None, clean: bool = True, dry_run: bool = False
) -> BuildResult:
    """Build and install one isolated profile."""

    paths = BuildPaths(spec)

    jobs = jobs or max(1, os.cpu_count() or 1)
    configure_cmd = [
        str(paths.work_src / "configure"),
        f"--prefix={paths.prefix}",
        *spec.profile.configure,
    ]
    build_cmd = ["make", f"-j{jobs}"]
    install_cmd = ["make", "install"]
    env = spec.profile.environment(os.environ)

    if dry_run:
        print(f"source: {paths.source}")
        print(f"work: {paths.work_root}")
        print(f"prefix: {paths.prefix}")
        print(f"configure: {shlex.join(configure_cmd)}")
        print("environment:")
        for name in DRY_RUN_ENV_KEYS:
            if name in env:
                print(f"  {name}={shlex.quote(env[name])}")
        print(f"build: {shlex.join(build_cmd)}")
        print(f"install: {shlex.join(install_cmd)}")
        return BuildResult(paths=paths, status="dry-run", metadata={})

    verify_source(spec)

    if paths.work_root.exists() and not clean:
        raise BuildError(
            f"build directory already exists: {paths.work_root}; "
            f"rerun with clean enabled or remove it explicitly"
        )

    log(f"preparing {spec.version.tag} {spec.target.name} {spec.profile.name}")
    remove_tree(paths.work_root)
    remove_tree(paths.prefix)
    remove_tree(paths.results_dir)
    paths.build_dir.mkdir(parents=True, exist_ok=True)
    paths.prefix.mkdir(parents=True, exist_ok=True)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)
    copy_tree(paths.source, paths.work_src)

    started_at = utc_now()
    started = time.monotonic()
    patches: list[str] = []
    effective_flags: dict[str, str] = {}
    installed: dict[str, Any] = {}
    _save_metadata(
        spec,
        paths,
        status="running",
        started_at=started_at,
        patches=patches,
        effective_flags=effective_flags,
        installed=installed,
        jobs=jobs,
    )

    try:
        patches = _apply_patches(spec, paths.work_src, paths.logs_dir)
        log(f"configuring {spec.profile.name}")
        configured = run_command(
            configure_cmd,
            cwd=paths.build_dir,
            env=env,
            log_path=paths.logs_dir / "configure.log",
            check=False,
        )
        if configured.returncode != 0:
            raise BuildError(f"configure failed; see {configured.log_path}")

        effective_flags = _flags_in_makefile(paths.build_dir / "Makefile")
        log(f"building {spec.profile.name} with {jobs} jobs")
        built = run_command(
            build_cmd,
            cwd=paths.build_dir,
            env=env,
            log_path=paths.logs_dir / "build.log",
            check=False,
        )
        if built.returncode != 0:
            raise BuildError(f"build failed; see {built.log_path}")

        log(f"installing into {paths.prefix}")
        install_env = python_runtime_env(paths.prefix)
        existing_library_path = install_env.get("LD_LIBRARY_PATH", "")
        install_env["LD_LIBRARY_PATH"] = str(paths.build_dir) + (
            f":{existing_library_path}" if existing_library_path else ""
        )
        installed_result = run_command(
            install_cmd,
            cwd=paths.build_dir,
            env=install_env,
            log_path=paths.logs_dir / "install.log",
            check=False,
        )
        if installed_result.returncode != 0:
            raise BuildError(f"install failed; see {installed_result.log_path}")

        installed = _verify_installed_build(spec, paths, effective_flags)
        installed["rpath"] = _set_install_rpath(paths, Path(installed["python"]))
        installed["duration_s"] = round(time.monotonic() - started, 3)
        metadata = _save_metadata(
            spec,
            paths,
            status="built",
            started_at=started_at,
            patches=patches,
            effective_flags=effective_flags,
            installed=installed,
            jobs=jobs,
        )
        log(f"built {spec.version.tag} {spec.profile.name}: {installed['python']}")
        return BuildResult(paths=paths, status="built", metadata=metadata)
    except Exception as error:
        _save_metadata(
            spec,
            paths,
            status="failed",
            started_at=started_at,
            patches=patches,
            effective_flags=effective_flags,
            installed=installed,
            jobs=jobs,
            error=str(error),
        )
        raise
