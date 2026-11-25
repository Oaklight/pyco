"""Aggregate metrics into summary.csv and report.md."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .config import Config, load_config
from .util import log, read_json, utc_now

CSV_FIELDS = [
    "cpython_version",
    "cpython_tag",
    "cpython_commit_or_sha256",
    "pyco_commit",
    "zerodep_commit",
    "target",
    "profile",
    "toolchain",
    "configure_flags",
    "cflags",
    "ldflags",
    "core_unstripped_bytes",
    "core_stripped_bytes",
    "stdlib_source_data_bytes",
    "native_extensions_bytes",
    "installed_total_bytes",
    "installed_prefix_bytes",
    "external_shared_libs",
    "archive_bytes",
    "default_distribution",
    "distribution_metrics",
    "startup_ms_median",
    "rss_kib",
    "cpython_tests",
    "zerodep_tests",
    "extension_inventory_diff",
    "abi_result",
    "package_smoke_result",
    "eligible",
    "failure_reasons",
]


def _as_text_list(value: Any) -> list[str]:
    """Normalize a metrics field that may be a string or a sequence."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]


def _row(metrics: dict[str, Any]) -> dict[str, Any]:
    toolchain = metrics.get("toolchain", {})
    if isinstance(toolchain, dict):
        toolchain_text = "; ".join(
            f"{key}={value}" for key, value in toolchain.items() if value
        )
    else:
        toolchain_text = str(toolchain)
    external = metrics.get("external_shared_libs", [])
    failures = _as_text_list(metrics.get("failure_reasons"))
    raw_distributions = metrics.get("distributions", {})
    distributions = raw_distributions if isinstance(raw_distributions, dict) else {}
    return {
        "cpython_version": metrics.get("cpython_version", ""),
        "cpython_tag": metrics.get("cpython_tag", ""),
        "cpython_commit_or_sha256": metrics.get("cpython_commit_or_sha256", ""),
        "pyco_commit": metrics.get("pyco_commit", ""),
        "zerodep_commit": metrics.get("zerodep_commit", ""),
        "target": metrics.get("target", ""),
        "profile": metrics.get("profile", ""),
        "toolchain": toolchain_text,
        "configure_flags": " ".join(metrics.get("configure_flags", [])),
        "cflags": metrics.get("cflags", ""),
        "ldflags": metrics.get("ldflags", ""),
        "core_unstripped_bytes": metrics.get("core_unstripped_bytes"),
        "core_stripped_bytes": metrics.get("core_stripped_bytes"),
        "stdlib_source_data_bytes": metrics.get("stdlib_source_data_bytes"),
        "native_extensions_bytes": metrics.get("native_extensions_bytes"),
        "installed_total_bytes": (
            metrics.get("packaged_installed_bytes")
            if metrics.get("packaged_installed_bytes") is not None
            else metrics.get("installed_total_bytes")
        ),
        "installed_prefix_bytes": metrics.get("installed_total_bytes"),
        "external_shared_libs": json.dumps(external, sort_keys=True),
        "archive_bytes": metrics.get("archive_bytes"),
        "default_distribution": metrics.get("default_distribution", ""),
        "distribution_metrics": json.dumps(distributions, sort_keys=True),
        "distributions": distributions,
        "startup_ms_median": metrics.get("startup_ms_median"),
        "rss_kib": metrics.get("rss_kib"),
        "cpython_tests": metrics.get("cpython_tests", "not-run"),
        "zerodep_tests": metrics.get("zerodep_tests", "not-run"),
        "extension_inventory_diff": metrics.get("extension_inventory_diff"),
        "abi_result": metrics.get("abi_result", "not-run"),
        "package_smoke_result": metrics.get("package_smoke_result", "not-run"),
        "eligible": metrics.get("eligible", False),
        "failure_reasons": "; ".join(failures),
    }


def _load_metrics(results_root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(results_root.glob("*/*/*/metrics.json")):
        data = read_json(path)
        data["_path"] = str(path)
        records.append(data)
    return sorted(
        records,
        key=lambda item: (
            str(item.get("cpython_tag", "")),
            str(item.get("target", "")),
            str(item.get("profile", "")),
        ),
    )


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _pareto(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    comparable = [
        row
        for row in rows
        if row.get("eligible")
        and _number(row.get("core_stripped_bytes")) is not None
        and _number(row.get("startup_ms_median")) is not None
        and _number(row.get("rss_kib")) is not None
    ]
    frontier: list[dict[str, Any]] = []
    for candidate in comparable:
        core = float(candidate["core_stripped_bytes"])
        startup = float(candidate["startup_ms_median"])
        rss = float(candidate["rss_kib"])
        dominated = False
        for other in comparable:
            if other is candidate:
                continue
            other_core = float(other["core_stripped_bytes"])
            other_startup = float(other["startup_ms_median"])
            other_rss = float(other["rss_kib"])
            if (
                other_core <= core
                and other_startup <= startup
                and other_rss <= rss
                and (other_core < core or other_startup < startup or other_rss < rss)
            ):
                dominated = True
                break
        if not dominated:
            frontier.append(candidate)
    return sorted(frontier, key=lambda row: float(row["core_stripped_bytes"]))


def _baseline_delta(rows: list[dict[str, Any]], row: dict[str, Any]) -> str:
    baselines = [
        candidate
        for candidate in rows
        if candidate.get("profile") == "baseline"
        and candidate.get("target") == row.get("target")
        and candidate.get("cpython_tag") == row.get("cpython_tag")
    ]
    if not baselines:
        return "no baseline"
    baseline = baselines[0]
    baseline_core = _number(baseline.get("core_stripped_bytes"))
    current_core = _number(row.get("core_stripped_bytes"))
    if baseline_core in (None, 0) or current_core is None:
        return "not comparable"
    delta = (current_core - baseline_core) / baseline_core * 100.0
    return f"{delta:+.2f}% core vs baseline"


def _format_bytes(value: Any) -> str:
    number = _number(value)
    if number is None:
        return "not measured"
    return f"{int(number):,}"


def _format_ms(value: Any) -> str:
    number = _number(value)
    if number is None:
        return "not measured"
    return f"{number:.3f} ms"


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in CSV_FIELDS})


def _write_report(path: Path, rows: list[dict[str, Any]], config: Config) -> None:
    lines = [
        "# Pyco measurement report",
        "",
        f"Generated: {utc_now()}",
        "",
        "No compatibility or size claim is valid unless the corresponding build is marked eligible.",
        "",
        "## Pins",
        "",
    ]
    for version in config.enabled_versions():
        lines.append(
            f"- CPython {version.version}: tag `{version.tag}`, commit `{version.git_commit}`, "
            f"SHA256 `{version.sha256}`"
        )
    lines.extend(
        [
            f"- zerodep: tag `{config.zerodep.tag}`, commit `{config.zerodep.commit}`",
            "",
        ]
    )
    if not rows:
        lines.extend(
            [
                "## Results",
                "",
                "No measurement records found. Run `./scripts/build.sh`, `./scripts/test.sh`, "
                "and `./scripts/measure.sh` first.",
                "",
            ]
        )
        path.write_text("\n".join(lines), encoding="utf-8")
        return

    lines.extend(
        [
            "## Matrix",
            "",
            "| Version | Target | Profile | Core stripped | Installed | Startup | RSS | Eligible |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in rows:
        lines.append(
            "| {version} | {target} | {profile} | {core} | {installed} | {startup} | {rss} | {eligible} |".format(
                version=row.get("cpython_version", ""),
                target=row.get("target", ""),
                profile=row.get("profile", ""),
                core=_format_bytes(row.get("core_stripped_bytes")),
                installed=_format_bytes(row.get("installed_total_bytes")),
                startup=_format_ms(row.get("startup_ms_median")),
                rss=_format_bytes(row.get("rss_kib")),
                eligible="yes" if row.get("eligible") else "no",
            )
        )
    lines.extend(["", "## Distribution variants", ""])
    has_variants = False
    for row in rows:
        raw_variants = row.get("distributions")
        if isinstance(raw_variants, dict) and raw_variants:
            has_variants = True
            break
    if not has_variants:
        lines.append("No packaged distribution variants are recorded.")
    else:
        lines.append(
            "| Version | Target | Profile | Distribution | Installed | Archive | Smoke |"
        )
        lines.append("| --- | --- | --- | --- | ---: | ---: | --- |")
        for row in rows:
            raw_variants = row.get("distributions")
            if not isinstance(raw_variants, dict):
                continue
            for name in sorted(raw_variants):
                info = raw_variants[name]
                if not isinstance(info, dict):
                    continue
                label = name
                if name == row.get("default_distribution"):
                    label = f"{name} (default)"
                lines.append(
                    "| {version} | {target} | {profile} | {name} | {installed} | {archive} | {status} |".format(
                        version=row.get("cpython_version", ""),
                        target=row.get("target", ""),
                        profile=row.get("profile", ""),
                        name=label,
                        installed=_format_bytes(info.get("installed_bytes")),
                        archive=_format_bytes(info.get("archive_bytes")),
                        status=info.get("status", "not-run"),
                    )
                )
    lines.extend(["", "## Baseline deltas", ""])
    for row in rows:
        lines.append(f"- {row.get('profile')}: {_baseline_delta(rows, row)}")
    lines.extend(["", "## Pareto frontier", ""])
    frontier = _pareto(rows)
    if not frontier:
        lines.append(
            "No eligible build has complete size, startup, and RSS measurements."
        )
    else:
        lines.append("| Profile | Core stripped | Startup | RSS |")
        lines.append("| --- | ---: | ---: | ---: |")
        for row in frontier:
            lines.append(
                "| {profile} | {core} | {startup} | {rss} |".format(
                    profile=row.get("profile", ""),
                    core=_format_bytes(row.get("core_stripped_bytes")),
                    startup=_format_ms(row.get("startup_ms_median")),
                    rss=_format_bytes(row.get("rss_kib")),
                )
            )
    lines.extend(["", "## Failures and missing gates", ""])
    any_failure = False
    for row in rows:
        reasons = _as_text_list(row.get("failure_reasons"))
        if reasons:
            any_failure = True
            lines.append(f"- {row.get('profile')}: {'; '.join(reasons)}")
    if not any_failure:
        lines.append("No recorded failure reasons.")
    lines.extend(
        [
            "",
            "## Measurement notes",
            "",
            "- Core bytes count the executable plus shared libpython when present.",
            "- Symlinks and hardlinks count once.",
            "- Startup measurements are warm-cache medians; no cold-cache claim is made.",
            "- Installed bytes include the stdlib, extensions, headers, and metadata under the prefix.",
            "- Matrix installed and archive bytes describe the default distribution; variant rows report each archive separately.",
            "- Archive bytes are reported separately from installed bytes.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def report(
    config: Config | None = None, results_root: Path | None = None
) -> tuple[Path, Path]:
    """Write results/summary.csv and results/report.md."""

    config = config or load_config()
    results_root = results_root or config.root / "results"
    rows = [_row(metrics) for metrics in _load_metrics(results_root)]
    summary = results_root / "summary.csv"
    report_path = results_root / "report.md"
    _write_csv(summary, rows)
    _write_report(report_path, rows, config)
    log(f"wrote {summary} and {report_path}")
    return summary, report_path
