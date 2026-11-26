"""Canonical output paths for one build cell."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from . import __version__
from .config import BuildSpec
from .distributions import DEFAULT_DISTRIBUTION


@dataclass(frozen=True)
class BuildPaths:
    """All generated paths for one version, target, and profile."""

    spec: BuildSpec

    @property
    def root(self) -> Path:
        return self.spec.root

    @property
    def tag(self) -> str:
        return self.spec.version.tag

    @property
    def version(self) -> str:
        return self.spec.version.version

    @property
    def target(self) -> str:
        return self.spec.target.name

    @property
    def profile(self) -> str:
        return self.spec.profile.name

    @property
    def source(self) -> Path:
        return self.root / self.spec.version.source_dir

    @property
    def archive(self) -> Path:
        return self.root / "sources" / "archives" / f"Python-{self.version}.tar.xz"

    @property
    def source_state(self) -> Path:
        return self.root / "sources" / ".state" / f"cpython-{self.version}.json"

    @property
    def work_root(self) -> Path:
        return self.root / "work" / self.tag / self.target / self.profile

    @property
    def work_src(self) -> Path:
        return self.work_root / "src"

    @property
    def build_dir(self) -> Path:
        return self.work_root / "build"

    @property
    def prefix(self) -> Path:
        return self.root / "out" / self.tag / self.target / self.profile

    @property
    def results_dir(self) -> Path:
        return self.root / "results" / self.tag / self.target / self.profile

    @property
    def logs_dir(self) -> Path:
        return self.results_dir / "logs"

    @property
    def build_metadata(self) -> Path:
        return self.results_dir / "build.json"

    @property
    def tests_metadata(self) -> Path:
        return self.results_dir / "tests.json"

    @property
    def metrics_metadata(self) -> Path:
        return self.results_dir / "metrics.json"

    @property
    def package_metadata(self) -> Path:
        return self.results_dir / "package.json"

    @property
    def package_archive(self) -> Path:
        return self.package_archive_for(DEFAULT_DISTRIBUTION)

    def package_archive_for(self, distribution: str) -> Path:
        release = os.environ.get("SNUGPY_RELEASE", __version__)
        return (
            self.root
            / "dist"
            / (
                f"snugpy-{release}-cpython{self.version}-{self.target}-"
                f"{self.profile}-{distribution}.tar.xz"
            )
        )
