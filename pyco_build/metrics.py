"""Measure installed size, dependencies, startup, and RSS."""

from __future__ import annotations

import json
import re
import shlex
import shutil
import statistics
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

from .config import BuildSpec, Config
from .distributions import DEFAULT_DISTRIBUTION
from .paths import BuildPaths
from .util import (
    PycoError,
    find_python,
    git_commit,
    is_elf,
    iter_unique_regular_files,
    log,
    python_runtime_env,
    read_json,
    run_command,
    sha256_file,
    utc_now,
    write_json,
)


class MetricsError(PycoError):
    """Raised when measurement cannot be completed."""


def _stdlib_root(prefix: Path) -> Path:
    candidates = sorted((prefix / "lib").glob("python3.*"))
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise MetricsError(f"no stdlib directory found under {prefix / 'lib'}")


def _core_files(prefix: Path, version: str) -> list[Path]:
    python = find_python(prefix, version)
    files = [python]
    library_dir = prefix / "lib"
    if library_dir.exists():
        for path, _ in iter_unique_regular_files(
            library_dir,
            lambda item: item.name.startswith("libpython") and ".so" in item.name,
        ):
            files.append(path)
    return sorted(set(files))


def _stdlib_predicate(root: Path) -> Callable[[Path], bool]:
    def predicate(path: Path) -> bool:
        relative = path.relative_to(root)
        parts = relative.parts
        if any(
            part in {"lib-dynload", "site-packages", "__pycache__"} for part in parts
        ):
            return False
        if parts and parts[0].startswith("config-"):
            return False
        if path.name.startswith("_sysconfigdata_"):
            return False
        return path.suffix not in {".pyc", ".pyo", ".so", ".a", ".o"}

    return predicate


def _extension_predicate(root: Path) -> Callable[[Path], bool]:
    def predicate(path: Path) -> bool:
        relative = path.relative_to(root)
        if "site-packages" in relative.parts:
            return False
        return path.suffix in {".so", ".pyd"}

    return predicate


def _ldd(binary: Path, env: dict[str, str] | None = None) -> list[dict[str, Any]]:
    result = run_command(["ldd", str(binary)], env=env, check=False)
    libraries: list[dict[str, Any]] = []
    for line in result.output.splitlines():
        line = line.strip()
        if not line or "=>" not in line:
            continue
        name, remainder = line.split("=>", 1)
        path_text = remainder.split("(", 1)[0].strip()
        if not path_text or path_text == "not found":
            libraries.append({"name": name.strip(), "path": None, "bytes": 0})
            continue
        path = Path(path_text).resolve()
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        libraries.append({"name": name.strip(), "path": str(path), "bytes": size})
    return libraries


def _external_libraries(core_files: list[Path], prefix: Path) -> list[dict[str, Any]]:
    seen: set[str] = set()
    libraries: list[dict[str, Any]] = []
    for binary in core_files:
        for entry in _ldd(binary, python_runtime_env(prefix)):
            path_text = entry.get("path")
            if not path_text:
                key = f"missing:{entry['name']}"
                if key not in seen:
                    seen.add(key)
                    libraries.append(entry)
                continue
            path = Path(str(path_text))
            if path == prefix or prefix in path.parents:
                continue
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            libraries.append(entry)
    return libraries


def _strip_copy(core_files: list[Path]) -> tuple[int | None, str | None]:
    strip = shutil.which("strip")
    if strip is None:
        return None, "strip not found"
    total = 0
    try:
        with tempfile.TemporaryDirectory(prefix="pyco-strip-") as directory:
            for index, path in enumerate(core_files):
                if not is_elf(path):
                    continue
                destination = Path(directory) / f"{index}-{path.name}"
                shutil.copy2(path, destination)
                result = subprocess.run(
                    [strip, "--strip-unneeded", str(destination)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode != 0:
                    return None, f"strip failed for {path}: {result.stderr.strip()}"
                total += destination.stat().st_size
    except OSError as error:
        return None, str(error)
    return total, None


def _hyperfine_statistics(
    data: dict[str, object], result: dict[str, object]
) -> dict[str, object]:
    """Return the timing statistics from either Hyperfine JSON schema."""

    summary = result.get("summary")
    if isinstance(summary, dict) and summary:
        metric = str(data.get("primary_metric") or "time_wall_clock")
        statistics = summary.get(metric)
        if not isinstance(statistics, dict):
            statistics = summary.get("time_wall_clock")
        if not isinstance(statistics, dict):
            statistics = next(
                (value for value in summary.values() if isinstance(value, dict)),
                None,
            )
        if isinstance(statistics, dict):
            return statistics
    return result


def _parse_hyperfine(path: Path, command: list[str], runs: int) -> dict[str, float]:
    data = json.loads(path.read_text(encoding="utf-8"))
    result = data["results"][0]
    statistics = _hyperfine_statistics(data, result)
    measurements = result.get("measurements")
    effective_runs = (
        len(measurements) if isinstance(measurements, list) and measurements else runs
    )
    try:
        return {
            "median_ms": float(statistics["median"]) * 1000.0,
            "mean_ms": float(statistics["mean"]) * 1000.0,
            "min_ms": float(statistics["min"]) * 1000.0,
            "max_ms": float(statistics["max"]) * 1000.0,
            "stddev_ms": float(statistics.get("stddev", 0.0)) * 1000.0,
            "runs": effective_runs,
            "command": shlex.join(command),
        }
    except (KeyError, TypeError, ValueError) as error:
        raise MetricsError(
            f"unsupported Hyperfine JSON schema in {path}: {error}"
        ) from error


def _measure_fallback(
    command: list[str],
    prefix: Path,
    runs: int,
    warmup: int = 3,
) -> dict[str, float]:
    env = python_runtime_env(prefix)
    durations: list[float] = []
    for index in range(warmup + runs):
        started = time.perf_counter()
        result = subprocess.run(
            command,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        elapsed = (time.perf_counter() - started) * 1000.0
        if index >= warmup:
            durations.append(elapsed)
        if result.returncode != 0:
            raise MetricsError(f"timing command failed: {shlex.join(command)}")
    return {
        "median_ms": statistics.median(durations),
        "mean_ms": statistics.fmean(durations),
        "min_ms": min(durations),
        "max_ms": max(durations),
        "stddev_ms": statistics.pstdev(durations) if len(durations) > 1 else 0.0,
        "runs": runs,
        "command": shlex.join(command),
    }


def _measure_command(
    command: list[str],
    prefix: Path,
    output_dir: Path,
    name: str,
    runs: int,
) -> dict[str, Any]:
    hyperfine = shutil.which("hyperfine")
    if hyperfine is not None:
        export = output_dir / f"hyperfine-{name}.json"
        result = run_command(
            [
                hyperfine,
                "--warmup",
                "3",
                "--runs",
                str(runs),
                "--style",
                "none",
                "--export-json",
                str(export),
                "--",
                shlex.join(command),
            ],
            env=python_runtime_env(prefix),
            log_path=output_dir / f"hyperfine-{name}.log",
            check=False,
        )
        if result.returncode == 0 and export.exists():
            measured = _parse_hyperfine(export, command, runs)
            measured["tool"] = "hyperfine"
            return measured
        log(f"hyperfine failed for {name}; using subprocess timer")
    measured = _measure_fallback(command, prefix, runs)
    measured["tool"] = "python-subprocess"
    return measured


def _peak_rss(command: list[str], prefix: Path) -> tuple[int | None, str | None]:
    time_binary = shutil.which("time")
    if time_binary is None:
        fallback = Path("/usr/bin/time")
        time_binary = str(fallback) if fallback.exists() else None
    if time_binary is None:
        return None, "GNU time binary not found"
    result = run_command(
        [time_binary, "-v", *command],
        env=python_runtime_env(prefix),
        check=False,
    )
    match = re.search(r"Maximum resident set size \(kbytes\):\s*(\d+)", result.output)
    if not match:
        return None, "peak RSS not reported"
    return int(match.group(1)), None


def _distribution_metrics(metadata: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Normalize per-distribution package metadata for reports."""

    raw = metadata.get("variants")
    if not isinstance(raw, dict):
        return {}
    distributions: dict[str, dict[str, Any]] = {}
    for name, value in raw.items():
        if not isinstance(value, dict):
            continue
        distributions[str(name)] = {
            "description": value.get("description", ""),
            "archive": value.get("archive"),
            "archive_format": value.get("archive_format"),
            "archive_bytes": value.get("archive_bytes"),
            "archive_sha256": value.get("archive_sha256"),
            "installed_bytes": value.get("installed_bytes"),
            "status": value.get("status", "not-run"),
        }
    return distributions


def _package_info(paths: BuildPaths) -> dict[str, Any]:
    metadata = (
        read_json(paths.package_metadata) if paths.package_metadata.exists() else {}
    )
    distributions = _distribution_metrics(metadata)
    default_name = str(metadata.get("default_distribution") or DEFAULT_DISTRIBUTION)
    default = distributions.get(default_name)
    if default is None:
        archive = paths.package_archive
        default = {
            "archive": str(archive) if archive.exists() else None,
            "archive_bytes": archive.stat().st_size if archive.exists() else None,
            "archive_sha256": (
                metadata.get("archive_sha256")
                or (sha256_file(archive) if archive.exists() else None)
            ),
            "archive_format": metadata.get("archive_format"),
            "installed_bytes": metadata.get("installed_bytes"),
            "status": metadata.get("status", "not-run"),
        }
        if archive.exists() or metadata:
            distributions[default_name] = default
    return {
        "default_distribution": default_name,
        "path": default.get("archive"),
        "bytes": default.get("archive_bytes"),
        "sha256": default.get("archive_sha256"),
        "installed_bytes": default.get("installed_bytes"),
        "status": default.get("status", "not-run"),
        "archive_format": default.get("archive_format"),
        "distributions": distributions,
    }


def _test_gate_status(tests: dict[str, Any] | None, name: str) -> str:
    if not tests:
        return "not-run"
    for gate in tests.get("gates", []):
        if gate.get("name") == name:
            return str(gate.get("status", "unknown"))
    return "not-run"


def measure(
    spec: BuildSpec,
    config: Config,
    *,
    runs: int = 10,
    skip_perf: bool = False,
) -> dict[str, Any]:
    """Collect metrics and write metrics.json."""

    paths = BuildPaths(spec)
    if not paths.prefix.exists():
        raise MetricsError(f"install prefix missing: {paths.prefix}; run build first")
    build = read_json(paths.build_metadata) if paths.build_metadata.exists() else {}
    tests = read_json(paths.tests_metadata) if paths.tests_metadata.exists() else None

    python = find_python(paths.prefix, spec.version.version)
    core = _core_files(paths.prefix, spec.version.version)
    core_bytes = sum(path.stat().st_size for path in core)
    stripped_bytes, strip_error = _strip_copy(core)
    stdlib = _stdlib_root(paths.prefix)
    stdlib_bytes = sum(
        info.st_size
        for _, info in iter_unique_regular_files(stdlib, _stdlib_predicate(stdlib))
    )
    extension_files = [
        path
        for path, _ in iter_unique_regular_files(stdlib, _extension_predicate(stdlib))
    ]
    extensions_bytes = sum(path.stat().st_size for path in extension_files)
    installed_bytes = sum(
        info.st_size for _, info in iter_unique_regular_files(paths.prefix)
    )
    external = _external_libraries(core, paths.prefix)
    external_bytes = sum(int(entry["bytes"]) for entry in external)

    output_dir = paths.results_dir / "measurements"
    output_dir.mkdir(parents=True, exist_ok=True)
    startup: dict[str, Any] = {}
    rss: dict[str, Any] = {}
    workloads: dict[str, Any] = {}
    if not skip_perf:
        startup = {
            "startup_s": _measure_command(
                [str(python), "-S", "-c", "pass"],
                paths.prefix,
                output_dir,
                "startup_s",
                runs,
            ),
            "startup_normal": _measure_command(
                [str(python), "-c", "pass"],
                paths.prefix,
                output_dir,
                "startup_normal",
                runs,
            ),
            "startup_imports": _measure_command(
                [str(python), "-c", "import asyncio, ssl, sqlite3"],
                paths.prefix,
                output_dir,
                "startup_imports",
                runs,
            ),
        }
        rss_normal, rss_error = _peak_rss([str(python), "-c", "pass"], paths.prefix)
        rss = {
            "startup_normal_kib": rss_normal,
            "error": rss_error,
        }
        workloads = {
            "cpu": _measure_command(
                [
                    str(python),
                    str(spec.root / "benchmarks" / "workloads" / "cpu_bound.py"),
                ],
                paths.prefix,
                output_dir,
                "cpu",
                runs,
            ),
            "io": _measure_command(
                [
                    str(python),
                    str(spec.root / "benchmarks" / "workloads" / "io_bound.py"),
                ],
                paths.prefix,
                output_dir,
                "io",
                runs,
            ),
        }
        cpu_rss, _ = _peak_rss(
            [str(python), str(spec.root / "benchmarks" / "workloads" / "cpu_bound.py")],
            paths.prefix,
        )
        io_rss, _ = _peak_rss(
            [str(python), str(spec.root / "benchmarks" / "workloads" / "io_bound.py")],
            paths.prefix,
        )
        workloads["cpu"]["rss_kib"] = cpu_rss
        workloads["io"]["rss_kib"] = io_rss

    package = _package_info(paths)
    startup_normal = startup.get("startup_normal", {})
    startup_imports = startup.get("startup_imports", {})
    if not isinstance(startup_normal, dict):
        startup_normal = {}
    if not isinstance(startup_imports, dict):
        startup_imports = {}
    failure_reasons: list[str] = []
    if tests:
        for gate in tests.get("gates", []):
            if gate.get("status") in {"fail", "skip"} and gate.get("required"):
                failure_reasons.append(f"{gate.get('name')}: {gate.get('status')}")

    toolchain = build.get("toolchain", {}) if isinstance(build, dict) else {}
    metrics: dict[str, Any] = {
        "schema_version": 1,
        "cpython_version": spec.version.version,
        "cpython_tag": spec.version.tag,
        "cpython_commit_or_sha256": spec.version.git_commit,
        "cpython_sha256": spec.version.sha256,
        "pyco_commit": git_commit(spec.root),
        "zerodep_commit": config.zerodep.commit,
        "target": spec.target.name,
        "profile": spec.profile.name,
        "toolchain": {
            "cc": toolchain.get("cc", ""),
            "ld": toolchain.get("ld", ""),
            "make": toolchain.get("make", ""),
        },
        "configure_flags": list(spec.profile.configure),
        "cflags": spec.profile.cflags,
        "ldflags": spec.profile.ldflags,
        "core_unstripped_bytes": core_bytes,
        "core_stripped_bytes": stripped_bytes,
        "core_strip_error": strip_error,
        "stdlib_source_data_bytes": stdlib_bytes,
        "native_extensions_bytes": extensions_bytes,
        "native_extension_count": len(extension_files),
        "installed_total_bytes": installed_bytes,
        "packaged_installed_bytes": package.get("installed_bytes"),
        "external_shared_libs": external,
        "external_shared_libs_bytes": external_bytes,
        "archive_bytes": package["bytes"],
        "archive_format": package.get("archive_format"),
        "archive_sha256": package["sha256"],
        "default_distribution": package.get("default_distribution"),
        "distributions": package.get("distributions", {}),
        "startup_ms": startup,
        "startup_ms_median": startup_normal.get("median_ms"),
        "startup_imports_ms_median": startup_imports.get("median_ms"),
        "rss_kib": rss.get("startup_normal_kib"),
        "rss": rss,
        "workloads": workloads,
        "cpython_tests": _test_gate_status(tests, "cpython regression"),
        "zerodep_tests": _test_gate_status(tests, "zerodep tests"),
        "abi_result": _test_gate_status(tests, "abi import"),
        "package_smoke_result": package.get("status", "not-run"),
        "extension_inventory_diff": None,
        "eligible": bool(tests.get("eligible")) if tests else False,
        "validation_status": tests.get("status") if tests else "not-run",
        "failure_reasons": failure_reasons,
        "measurement": {
            "tool": startup.get("startup_normal", {}).get("tool", "not-run"),
            "runs": runs,
            "skip_perf": skip_perf,
            "measured_at": utc_now(),
            "cache_state": "warm process cache" if not skip_perf else "not measured",
        },
        "notes": [
            "Core bytes count the executable and shared libpython; symlinks and hardlinks count once.",
            "Installed total uses the stripped packaged tree when available; installed_prefix_bytes retains the unstripped prefix size.",
        ],
    }
    write_json(paths.metrics_metadata, metrics)
    log(
        f"measured {spec.version.tag} {spec.profile.name}: "
        f"core={core_bytes} bytes, installed={installed_bytes} bytes"
    )
    return metrics
