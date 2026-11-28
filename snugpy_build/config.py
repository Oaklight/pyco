"""Load version, target, profile, and zerodep pins."""

from __future__ import annotations

import re

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

from dataclasses import dataclass
from pathlib import Path

from .profiles import ProfileError, ProfileSpec, load_profiles, resolve_profile
from .resources import config_dir
from .util import SnugPyError

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class ConfigError(SnugPyError):
    """Raised for invalid repository configuration."""


@dataclass(frozen=True)
class VersionPin:
    """One immutable CPython source pin."""

    key: str
    enabled: bool
    version: str
    tag: str
    url: str
    sha256: str
    git_commit: str
    source_dir: Path


@dataclass(frozen=True)
class TargetSpec:
    """One platform target."""

    name: str
    platform: str
    arch: str
    runner: str
    container_image: str
    glibc_baseline: str
    apt_packages: tuple[str, ...]
    notes: str


@dataclass(frozen=True)
class ZerodepPin:
    """The pinned zerodep compatibility target."""

    repo: str
    tag: str
    commit: str
    requires_python: str
    notes: str


@dataclass(frozen=True)
class ReleaseSelection:
    """Reviewed release selection for one version and target."""

    version_key: str
    target: str
    profile: str
    status: str
    approved: bool
    notes: str


@dataclass(frozen=True)
class BuildSpec:
    """A fully resolved build cell."""

    root: Path
    version: VersionPin
    target: TargetSpec
    profile: ProfileSpec


@dataclass(frozen=True)
class Config:
    """All repository configuration."""

    root: Path
    versions: dict[str, VersionPin]
    targets: dict[str, TargetSpec]
    profiles: dict[str, ProfileSpec]
    zerodep: ZerodepPin
    release_selection: tuple[ReleaseSelection, ...]

    def enabled_versions(self) -> list[VersionPin]:
        """Return enabled versions in key order."""

        return [
            self.versions[key]
            for key in sorted(self.versions)
            if self.versions[key].enabled
        ]

    def default_version(self) -> VersionPin:
        """Return the first enabled version."""

        enabled = self.enabled_versions()
        if not enabled:
            raise ConfigError("no enabled CPython versions")
        return enabled[0]

    def resolve(self, version: str, profile: str, target: str) -> BuildSpec:
        """Resolve CLI values into a build specification."""

        version_pin = self._resolve_version(version)
        try:
            target_spec = self.targets[target]
        except KeyError as error:
            available = ", ".join(sorted(self.targets))
            raise ConfigError(
                f"unknown target {target!r}; expected one of: {available}"
            ) from error
        try:
            profile_spec = resolve_profile(self.profiles, profile)
        except ProfileError as error:
            raise ConfigError(str(error)) from error
        return BuildSpec(
            root=self.root,
            version=version_pin,
            target=target_spec,
            profile=profile_spec,
        )

    def _resolve_version(self, value: str) -> VersionPin:
        matches = [
            pin
            for pin in self.versions.values()
            if value in {pin.key, pin.version, pin.tag}
        ]
        if not matches:
            available = ", ".join(sorted(self.versions))
            raise ConfigError(
                f"unknown CPython version {value!r}; expected one of: {available}"
            )
        pin = matches[0]
        if not pin.enabled:
            raise ConfigError(
                f"CPython version {pin.version} is configured but disabled"
            )
        return pin


def _require_table(data: object, name: str) -> dict[str, object]:
    if not isinstance(data, dict):
        raise ConfigError(f"{name} must be a table")
    return data


def _load_versions(path: Path, root: Path) -> dict[str, VersionPin]:
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    if data.get("schema_version") != 1:
        raise ConfigError(f"{path}: unsupported schema_version")
    raw_versions = _require_table(data.get("versions"), f"{path}: versions")
    versions: dict[str, VersionPin] = {}
    for key, raw_value in raw_versions.items():
        raw = _require_table(raw_value, f"{path}: versions.{key}")
        try:
            version = str(raw["version"])
            tag = str(raw["tag"])
            url = str(raw["url"])
            sha256 = str(raw["sha256"])
            git_commit = str(raw["git_commit"])
            source_dir = Path(str(raw["source_dir"]))
            enabled = bool(raw["enabled"])
        except KeyError as error:
            raise ConfigError(f"{path}: versions.{key} is missing {error}") from error
        if not SHA256_RE.fullmatch(sha256):
            raise ConfigError(f"{path}: versions.{key} has an invalid SHA256")
        if not COMMIT_RE.fullmatch(git_commit):
            raise ConfigError(f"{path}: versions.{key} has an invalid Git commit")
        if not url.startswith("https://"):
            raise ConfigError(f"{path}: versions.{key} must use an HTTPS URL")
        if source_dir.is_absolute() or ".." in source_dir.parts:
            raise ConfigError(
                f"{path}: versions.{key}.source_dir must stay under the repository"
            )
        versions[key] = VersionPin(
            key=key,
            enabled=enabled,
            version=version,
            tag=tag,
            url=url,
            sha256=sha256,
            git_commit=git_commit,
            source_dir=source_dir,
        )
    if not versions:
        raise ConfigError(f"{path}: no versions configured")
    return versions


def _load_targets(path: Path) -> dict[str, TargetSpec]:
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    if data.get("schema_version") != 1:
        raise ConfigError(f"{path}: unsupported schema_version")
    raw_targets = _require_table(data.get("targets"), f"{path}: targets")
    targets: dict[str, TargetSpec] = {}
    for name, raw_value in raw_targets.items():
        raw = _require_table(raw_value, f"{path}: targets.{name}")
        try:
            apt_packages = raw.get("apt_packages", [])
            target = TargetSpec(
                name=name,
                platform=str(raw["platform"]),
                arch=str(raw["arch"]),
                runner=str(raw["runner"]),
                container_image=str(raw["container_image"]),
                glibc_baseline=str(raw.get("glibc_baseline", "")),
                apt_packages=tuple(str(item) for item in apt_packages),
                notes=str(raw.get("notes", "")),
            )
        except (KeyError, TypeError) as error:
            raise ConfigError(f"{path}: invalid target {name!r}: {error}") from error
        if target.platform != "linux":
            raise ConfigError(f"{path}: target {name!r} is not Linux")
        targets[name] = target
    if not targets:
        raise ConfigError(f"{path}: no targets configured")
    return targets


def _load_zerodep(path: Path) -> ZerodepPin:
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    raw = _require_table(data.get("zerodep"), f"{path}: zerodep")
    try:
        pin = ZerodepPin(
            repo=str(raw["repo"]),
            tag=str(raw["tag"]),
            commit=str(raw["commit"]),
            requires_python=str(raw["requires_python"]),
            notes=str(raw.get("notes", "")),
        )
    except KeyError as error:
        raise ConfigError(f"{path}: zerodep is missing {error}") from error
    if not COMMIT_RE.fullmatch(pin.commit):
        raise ConfigError(f"{path}: zerodep has an invalid Git commit")
    return pin


def _load_release_selection(path: Path) -> tuple[ReleaseSelection, ...]:
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    if data.get("schema_version") != 1:
        raise ConfigError(f"{path}: unsupported schema_version")
    raw_selection = data.get("selection", {})
    if not isinstance(raw_selection, dict):
        raise ConfigError(f"{path}: selection must be a table")
    selections: list[ReleaseSelection] = []
    for version_key, targets in raw_selection.items():
        target_table = _require_table(targets, f"{path}: selection.{version_key}")
        for target, raw_value in target_table.items():
            raw = _require_table(raw_value, f"{path}: selection.{version_key}.{target}")
            selections.append(
                ReleaseSelection(
                    version_key=version_key,
                    target=target,
                    profile=str(raw.get("profile", "")),
                    status=str(raw.get("status", "unselected")),
                    approved=bool(raw.get("approved", False)),
                    notes=str(raw.get("notes", "")),
                )
            )
    return tuple(selections)


def _workspace_root() -> Path:
    """Return the working tree, or the current directory for installed use."""

    package_root = Path(__file__).resolve().parents[1]
    current = Path.cwd().resolve()
    if (current / "configs" / "versions.toml").is_file():
        return current
    if (package_root / "configs" / "versions.toml").is_file():
        return package_root
    return current


def load_config(root: Path | None = None) -> Config:
    """Load all configuration from configs/."""

    repo_root = (root or _workspace_root()).resolve()
    configs = config_dir(repo_root)
    versions = _load_versions(configs / "versions.toml", repo_root)
    targets = _load_targets(configs / "targets.toml")
    profiles = load_profiles(configs / "profiles.toml")
    zerodep = _load_zerodep(configs / "versions.toml")
    release_selection = _load_release_selection(configs / "release-selection.toml")
    config = Config(
        root=repo_root,
        versions=versions,
        targets=targets,
        profiles=profiles,
        zerodep=zerodep,
        release_selection=release_selection,
    )
    for version in config.enabled_versions():
        config.resolve(
            version.key, next(iter(config.profiles)), next(iter(config.targets))
        )
    return config
