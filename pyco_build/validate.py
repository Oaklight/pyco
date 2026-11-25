"""Compatibility and smoke validation for one installed build."""

from __future__ import annotations

import json
import os
import shlex
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from .config import BuildSpec
from .paths import BuildPaths
from .source import fetch_zerodep
from .util import (
    PycoError,
    copy_tree,
    find_python,
    log,
    python_runtime_env,
    remove_tree,
    run_command,
    utc_now,
    write_json,
)


class ValidationError(PycoError):
    """Raised when a build cannot be validated."""


@dataclass
class GateResult:
    """One validation gate."""

    name: str
    category: str
    required: bool
    status: str
    command: str | None
    log: str | None
    duration_s: float
    detail: str


@dataclass(frozen=True)
class ValidationResult:
    """Summary of all validation gates."""

    metadata: dict[str, Any]
    status: str
    smoke_passed: bool
    eligible: bool


def _slug(name: str) -> str:
    return name.replace("/", "-").replace(" ", "-").lower()


def _append_jsonl(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(data, sort_keys=True) + "\n")


def _run_gate(
    spec: BuildSpec,
    prefix: Path,
    tests_root: Path,
    gates: list[GateResult],
    name: str,
    category: str,
    command: list[str],
    *,
    required: bool = True,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
    validator: Callable[[str], str | None] | None = None,
) -> GateResult:
    started = time.monotonic()
    log_path = tests_root / "logs" / f"{_slug(name)}.log"
    result = run_command(
        command,
        cwd=cwd,
        env=env if env is not None else python_runtime_env(prefix),
        log_path=log_path,
        check=False,
        timeout=timeout,
    )
    status = "pass" if result.returncode == 0 else "fail"
    detail = ""
    if result.returncode != 0:
        detail = f"exit code {result.returncode}"
    elif validator is not None:
        problem = validator(result.output)
        if problem:
            status = "fail"
            detail = problem
    gate = GateResult(
        name=name,
        category=category,
        required=required,
        status=status,
        command=shlex.join(command),
        log=str(log_path.relative_to(spec.root)),
        duration_s=round(time.monotonic() - started, 3),
        detail=detail,
    )
    gates.append(gate)
    _append_jsonl(tests_root / "gates.jsonl", asdict(gate))
    return gate


def _skip_gate(
    tests_root: Path,
    gates: list[GateResult],
    name: str,
    category: str,
    reason: str,
    *,
    required: bool = True,
) -> GateResult:
    gate = GateResult(
        name=name,
        category=category,
        required=required,
        status="skip",
        command=None,
        log=None,
        duration_s=0.0,
        detail=reason,
    )
    gates.append(gate)
    _append_jsonl(tests_root / "gates.jsonl", asdict(gate))
    return gate


def _version_validator(expected: str) -> Callable[[str], str | None]:
    def validate(output: str) -> str | None:
        if expected not in output:
            return f"output does not contain expected version {expected}"
        return None

    return validate


def _sysconfig_validator(
    spec: BuildSpec, output_path: Path
) -> Callable[[str], str | None]:
    def validate(output: str) -> str | None:
        try:
            data = json.loads(output)
        except json.JSONDecodeError as error:
            return f"invalid sysconfig JSON: {error}"
        output_path.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        version = str(data.get("version", ""))
        if not version.startswith(spec.version.version):
            return (
                f"interpreter version {version!r} does not match {spec.version.version}"
            )
        shared = data.get("Py_ENABLE_SHARED")
        wants_shared = "--disable-shared" not in spec.profile.configure
        if bool(int(shared or 0)) != wants_shared:
            return f"Py_ENABLE_SHARED={shared!r}, requested shared={wants_shared}"
        return None

    return validate


def _check_abi(
    spec: BuildSpec, prefix: Path, tests_root: Path, gates: list[GateResult]
) -> None:
    python = find_python(prefix, spec.version.version)
    short = ".".join(spec.version.version.split(".")[:2])
    config_tool = prefix / "bin" / f"python{short}-config"
    if not config_tool.exists():
        _run_gate(
            spec,
            prefix,
            tests_root,
            gates,
            "abi extension",
            "abi",
            [str(config_tool), "--includes"],
            required=True,
        )
        return

    includes_result = run_command([str(config_tool), "--includes"], check=False)
    suffix_result = run_command([str(config_tool), "--extension-suffix"], check=False)
    if includes_result.returncode != 0 or suffix_result.returncode != 0:
        raise ValidationError("python-config could not report extension build flags")
    includes = shlex.split(includes_result.output.strip())
    suffix = suffix_result.output.strip()
    if not suffix:
        raise ValidationError("python-config returned an empty extension suffix")

    module_dir = tests_root / "abi"
    remove_tree(module_dir)
    module_dir.mkdir(parents=True)
    source = spec.root / "tests" / "abi_smoke" / "abi_smoke.c"
    module = module_dir / f"abi_smoke{suffix}"
    compile_command = [
        spec.profile.cc,
        "-shared",
        "-fPIC",
        *includes,
        str(source),
        "-o",
        str(module),
    ]
    compile_gate = _run_gate(
        spec,
        prefix,
        tests_root,
        gates,
        "abi compile",
        "abi",
        compile_command,
        required=True,
    )
    if compile_gate.status != "pass":
        return
    env = python_runtime_env(prefix)
    env["PYTHONPATH"] = str(module_dir)
    _run_gate(
        spec,
        prefix,
        tests_root,
        gates,
        "abi import",
        "abi",
        [
            str(python),
            "-c",
            "import abi_smoke; assert abi_smoke.ping(41) == 42; print('abi-ok')",
        ],
        required=True,
        env=env,
    )


def _check_zerodep(
    spec: BuildSpec,
    config: Any,
    prefix: Path,
    tests_root: Path,
    gates: list[GateResult],
    *,
    network: bool,
) -> None:
    zerodep_source = fetch_zerodep(config)
    copy_tree(zerodep_source, tests_root / "zerodep")
    python = find_python(prefix, spec.version.version)
    env = python_runtime_env(prefix)
    env["PYTHONPATH"] = str(tests_root / "zerodep")
    _run_gate(
        spec,
        prefix,
        tests_root,
        gates,
        "zerodep compileall",
        "zerodep",
        [str(python), "-m", "compileall", "-q", str(tests_root / "zerodep")],
        required=True,
        env=env,
    )
    _run_gate(
        spec,
        prefix,
        tests_root,
        gates,
        "zerodep import",
        "zerodep",
        [str(python), "-c", "import zerodep; print('zerodep-ok')"],
        required=True,
        env=env,
        cwd=tests_root / "zerodep",
    )
    if not network:
        _skip_gate(
            tests_root,
            gates,
            "zerodep tests",
            "zerodep",
            "network-disabled: pytest and comparison dependencies were not installed",
        )
        return
    venv = tests_root / "venv"
    if not (venv / "bin" / "python").exists():
        _skip_gate(
            tests_root,
            gates,
            "zerodep tests",
            "zerodep",
            "venv was not created",
        )
        return
    pip = venv / "bin" / "pip"
    install_gate = _run_gate(
        spec,
        prefix,
        tests_root,
        gates,
        "zerodep test dependencies",
        "zerodep",
        [
            str(pip),
            "install",
            "--disable-pip-version-check",
            "pytest",
            "pytest-asyncio",
            "pytest-benchmark",
        ],
        required=True,
        timeout=900,
    )
    if install_gate.status != "pass":
        return
    _run_gate(
        spec,
        prefix,
        tests_root,
        gates,
        "zerodep tests",
        "zerodep",
        ["make", "test", f"PYTHON={venv / 'bin' / 'python'}"],
        required=True,
        cwd=tests_root / "zerodep",
        env={
            **python_runtime_env(prefix),
            "PATH": f"{venv / 'bin'}:{os.environ.get('PATH', '')}",
        },
        timeout=3600,
    )


def validate(
    spec: BuildSpec,
    config: Any,
    *,
    mode: str = "smoke",
    jobs: int | None = None,
    network: bool = False,
    zerodep: bool = True,
) -> ValidationResult:
    """Run validation gates and write tests.json."""

    paths = BuildPaths(spec)
    if not paths.prefix.exists():
        raise ValidationError(
            f"install prefix missing: {paths.prefix}; run build first"
        )
    if not paths.build_metadata.exists():
        raise ValidationError(
            f"build metadata missing: {paths.build_metadata}; run build first"
        )

    python = find_python(paths.prefix, spec.version.version)
    tests_root = paths.results_dir / "tests"
    remove_tree(tests_root)
    tests_root.mkdir(parents=True)
    (tests_root / "logs").mkdir()
    (tests_root / "tmp").mkdir()

    started_at = utc_now()
    started = time.monotonic()
    gates: list[GateResult] = []

    _run_gate(
        spec,
        paths.prefix,
        tests_root,
        gates,
        "version",
        "smoke",
        [str(python), "-VV"],
        validator=_version_validator(spec.version.version),
    )
    sysconfig_code = (
        "import json, sys, sysconfig; "
        "print(json.dumps({"
        "'version': sys.version, "
        "'version_info': list(sys.version_info), "
        "'Py_ENABLE_SHARED': sysconfig.get_config_var('Py_ENABLE_SHARED'), "
        "'CONFIG_ARGS': sysconfig.get_config_var('CONFIG_ARGS') or '', "
        "'paths': sysconfig.get_paths(), "
        "'vars': {k: str(v) for k, v in sysconfig.get_config_vars().items()}"
        "}))"
    )
    _run_gate(
        spec,
        paths.prefix,
        tests_root,
        gates,
        "sysconfig",
        "smoke",
        [str(python), "-c", sysconfig_code],
        validator=_sysconfig_validator(spec, tests_root / "sysconfig.json"),
    )
    _run_gate(
        spec,
        paths.prefix,
        tests_root,
        gates,
        "ensurepip",
        "smoke",
        [str(python), "-m", "ensurepip", "--version"],
    )
    venv = tests_root / "venv"
    remove_tree(venv)
    venv_gate = _run_gate(
        spec,
        paths.prefix,
        tests_root,
        gates,
        "venv",
        "smoke",
        [str(python), "-m", "venv", str(venv)],
        timeout=900,
    )
    if venv_gate.status == "pass":
        _run_gate(
            spec,
            paths.prefix,
            tests_root,
            gates,
            "venv interpreter",
            "smoke",
            [str(venv / "bin" / "python"), "-c", "print('venv-ok')"],
        )
    _run_gate(
        spec,
        paths.prefix,
        tests_root,
        gates,
        "runtime smoke",
        "smoke",
        [str(python), str(spec.root / "tests" / "smoke.py"), "--json"],
        timeout=300,
    )
    _check_abi(spec, paths.prefix, tests_root, gates)
    if zerodep:
        _check_zerodep(spec, config, paths.prefix, tests_root, gates, network=network)

    if mode == "full":
        tmp_dir = tests_root / "tmp"
        env = python_runtime_env(paths.prefix)
        env["TMPDIR"] = str(tmp_dir)
        _run_gate(
            spec,
            paths.prefix,
            tests_root,
            gates,
            "cpython regression",
            "full",
            [
                str(python),
                "-m",
                "test",
                f"-j{jobs or os.cpu_count() or 1}",
                "--timeout",
                "1200",
            ],
            cwd=tests_root,
            env=env,
            timeout=7200,
        )
    else:
        _skip_gate(
            tests_root,
            gates,
            "cpython regression",
            "full",
            "smoke mode: full CPython regression suite not run",
        )

    failed = [gate for gate in gates if gate.status == "fail"]
    skipped = [gate for gate in gates if gate.status == "skip"]
    smoke_failed = [
        gate for gate in failed if gate.category in {"smoke", "abi", "zerodep"}
    ]
    smoke_passed = not smoke_failed
    eligible = mode == "full" and not failed and not skipped
    status = "failed" if failed else ("incomplete" if skipped else "passed")

    counts: dict[str, int] = {"pass": 0, "fail": 0, "skip": 0}
    for gate in gates:
        counts[gate.status] = counts.get(gate.status, 0) + 1

    metadata: dict[str, Any] = {
        "schema_version": 1,
        "version": spec.version.version,
        "cpython_tag": spec.version.tag,
        "cpython_commit": spec.version.git_commit,
        "target": spec.target.name,
        "profile": spec.profile.name,
        "mode": mode,
        "network": network,
        "status": status,
        "smoke_passed": smoke_passed,
        "eligible": eligible,
        "counts": counts,
        "gates": [asdict(gate) for gate in gates],
        "started_at": started_at,
        "finished_at": utc_now(),
        "duration_s": round(time.monotonic() - started, 3),
        "notes": [
            "Eligibility requires full CPython regression and zerodep tests.",
            "Network tests are skipped unless --network is set.",
        ],
    }
    write_json(paths.tests_metadata, metadata)
    log(
        f"validation {status}: {counts['pass']} pass, {counts['fail']} fail, "
        f"{counts['skip']} skip"
    )
    return ValidationResult(
        metadata=metadata,
        status=status,
        smoke_passed=smoke_passed,
        eligible=eligible,
    )
