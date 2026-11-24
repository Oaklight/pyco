"""Command-line interface for Pyco build orchestration."""

from __future__ import annotations

import argparse
from typing import Sequence

from . import __version__
from .build import build as build_cell
from .config import Config, load_config
from .metrics import measure as measure_cell
from .package import package as package_cell
from .paths import BuildPaths
from .report import report as report_cells
from .source import fetch_version, fetch_zerodep
from .util import PycoError, log
from .validate import validate


def _config() -> Config:
    return load_config()


def _target(config: Config, value: str | None) -> str:
    return value or next(iter(config.targets))


def _print_list(config: Config) -> None:
    print("Versions:")
    for key in sorted(config.versions):
        pin = config.versions[key]
        state = "enabled" if pin.enabled else "disabled"
        print(f"  {key}: {pin.version} ({pin.tag}, {state})")
    print("Targets:")
    for key in sorted(config.targets):
        print(f"  {key}: {config.targets[key].runner}")
    print("Profiles:")
    for key in sorted(config.profiles):
        profile = config.profiles[key]
        suffix = " (experimental)" if profile.experimental else ""
        print(f"  {key}: {profile.description}{suffix}")


def _cmd_fetch(config: Config, args: argparse.Namespace) -> int:
    spec = config.resolve(
        args.version, next(iter(config.profiles)), _target(config, args.target)
    )
    fetch_version(spec, force=args.force)
    if args.zerodep:
        fetch_zerodep(config, force=args.force)
    return 0


def _cmd_build(config: Config, args: argparse.Namespace) -> int:
    spec = config.resolve(args.version, args.profile, args.target)
    build_cell(spec, jobs=args.jobs, clean=not args.no_clean, dry_run=args.dry_run)
    return 0


def _cmd_test(config: Config, args: argparse.Namespace) -> int:
    spec = config.resolve(args.version, args.profile, args.target)
    result = validate(
        spec,
        config,
        mode=args.mode,
        jobs=args.jobs,
        network=args.network,
        zerodep=not args.no_zerodep,
    )
    if result.status == "failed":
        return 1
    if args.mode == "full" and not result.eligible:
        return 1
    return 0


def _cmd_measure(config: Config, args: argparse.Namespace) -> int:
    spec = config.resolve(args.version, args.profile, args.target)
    measure_cell(spec, config, runs=args.runs, skip_perf=args.skip_perf)
    return 0


def _cmd_package(config: Config, args: argparse.Namespace) -> int:
    spec = config.resolve(args.version, args.profile, args.target)
    package_cell(spec)
    return 0


def _cmd_report(config: Config, args: argparse.Namespace) -> int:
    report_cells(config)
    return 0


def _cmd_deps(config: Config, args: argparse.Namespace) -> int:
    target_name = _target(config, args.target)
    try:
        target = config.targets[target_name]
    except KeyError:
        raise PycoError(f"unknown target {target_name!r}") from None
    for package in target.apt_packages:
        print(package)
    return 0


def _cmd_paths(config: Config, args: argparse.Namespace) -> int:
    spec = config.resolve(args.version, args.profile, args.target)
    paths = BuildPaths(spec)
    print(f"source={paths.source}")
    print(f"work={paths.work_root}")
    print(f"build={paths.build_dir}")
    print(f"prefix={paths.prefix}")
    print(f"results={paths.results_dir}")
    print(f"archive={paths.package_archive}")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pyco", description=__doc__)
    parser.add_argument("--version", action="version", version=f"pyco {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch = subparsers.add_parser(
        "fetch", help="fetch and verify the pinned CPython source"
    )
    fetch.add_argument("version")
    fetch.add_argument("--target", default=None)
    fetch.add_argument(
        "--zerodep", action="store_true", help="also fetch the pinned zerodep source"
    )
    fetch.add_argument("--force", action="store_true")
    fetch.set_defaults(func=_cmd_fetch)

    build = subparsers.add_parser("build", help="build one isolated profile")
    build.add_argument("version")
    build.add_argument("profile")
    build.add_argument("target")
    build.add_argument("--jobs", type=int, default=None)
    build.add_argument("--no-clean", action="store_true")
    build.add_argument("--dry-run", action="store_true")
    build.set_defaults(func=_cmd_build)

    test = subparsers.add_parser("test", help="run smoke or full compatibility gates")
    test.add_argument("version")
    test.add_argument("profile")
    test.add_argument("target")
    test.add_argument(
        "--smoke", dest="mode", action="store_const", const="smoke", default="smoke"
    )
    test.add_argument("--full", dest="mode", action="store_const", const="full")
    test.add_argument("--jobs", type=int, default=None)
    test.add_argument(
        "--network", action="store_true", help="run tests that need network access"
    )
    test.add_argument("--no-zerodep", action="store_true", help="skip zerodep gates")
    test.set_defaults(func=_cmd_test)

    measure = subparsers.add_parser(
        "measure", help="measure size, dependencies, startup, and RSS"
    )
    measure.add_argument("version")
    measure.add_argument("profile")
    measure.add_argument("target")
    measure.add_argument("--runs", type=int, default=10)
    measure.add_argument("--skip-perf", action="store_true")
    measure.set_defaults(func=_cmd_measure)

    package = subparsers.add_parser(
        "package", help="create and verify a distribution archive"
    )
    package.add_argument("version")
    package.add_argument("profile")
    package.add_argument("target")
    package.set_defaults(func=_cmd_package)

    report = subparsers.add_parser(
        "report", help="aggregate metrics into summary.csv and report.md"
    )
    report.set_defaults(func=_cmd_report)

    deps = subparsers.add_parser("deps", help="print apt packages for a target")
    deps.add_argument("--target", default=None)
    deps.set_defaults(func=_cmd_deps)

    paths = subparsers.add_parser(
        "paths", help="print canonical paths for one build cell"
    )
    paths.add_argument("version")
    paths.add_argument("profile")
    paths.add_argument("target")
    paths.set_defaults(func=_cmd_paths)

    listing = subparsers.add_parser(
        "list", help="list configured versions, targets, and profiles"
    )
    listing.set_defaults(func=lambda config, args: (_print_list(config), 0)[1])
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI."""

    parser = _parser()
    args = parser.parse_args(argv)
    try:
        config = _config()
        return int(args.func(config, args))
    except PycoError as error:
        log(f"error: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
