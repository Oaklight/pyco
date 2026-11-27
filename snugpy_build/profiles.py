"""Build profile definitions and resolution."""

from __future__ import annotations

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .util import SnugPyError

# Conda activation exports optimized and hardened compiler flags. They are
# intentionally discarded so that each profile is compared from the same base.
_CONTAMINATING_FLAGS = (
    "CFLAGS",
    "CPPFLAGS",
    "CXXFLAGS",
    "LDFLAGS",
    "DEBUG_CFLAGS",
    "DEBUG_CXXFLAGS",
    "DEBUG_CPPFLAGS",
    "DEBUG_LDFLAGS",
    "FCFLAGS",
    "FFLAGS",
    "CPATH",
    "C_INCLUDE_PATH",
    "CPLUS_INCLUDE_PATH",
)


_SYSTEM_PKGCONFIG_DIRS = (
    "/usr/lib/x86_64-linux-gnu/pkgconfig",
    "/usr/lib/pkgconfig",
    "/usr/share/pkgconfig",
)


class ProfileError(SnugPyError):
    """Raised for invalid profile configuration."""


def _append_flag(environment: dict[str, str], name: str, value: str) -> None:
    """Append a non-empty flag string to one environment variable."""

    value = value.strip()
    if not value:
        return
    previous = environment.get(name, "").strip()
    environment[name] = f"{previous} {value}".strip()


@dataclass(frozen=True)
class ProfileSpec:
    """One compiler/linker profile."""

    name: str
    description: str
    cc: str
    cxx: str
    configure: tuple[str, ...]
    cflags: str
    cppflags: str
    cxxflags: str
    ldflags: str
    experimental: bool
    external_libs: str = "conda"

    def environment(self, base: Mapping[str, str] | None = None) -> dict[str, str]:
        """Return a clean toolchain environment for this profile.

        Args:
            base: Source environment. Defaults to the current process
                environment.

        Returns:
            A copy of the source environment with conda optimization flags
            removed, profile flags applied, and conda include/library paths
            supplied explicitly. ``SNUGPY_CONDA_PREFIX`` takes precedence over
            ``CONDA_PREFIX`` so CI can use a locked prefix without activating
            it.
        """

        environment = dict(base or {})
        for name in _CONTAMINATING_FLAGS:
            environment.pop(name, None)
        environment["CC"] = self.cc
        environment["CXX"] = self.cxx
        environment["CFLAGS"] = self.cflags.strip()
        environment["CPPFLAGS"] = self.cppflags.strip()
        environment["CXXFLAGS"] = self.cxxflags.strip()
        environment["LDFLAGS"] = self.ldflags.strip()

        prefix = environment.get("SNUGPY_CONDA_PREFIX") or environment.get(
            "CONDA_PREFIX"
        )
        if self.external_libs == "system":
            pkgconfig_dirs = ":".join(_SYSTEM_PKGCONFIG_DIRS)
            environment["PKG_CONFIG_PATH"] = pkgconfig_dirs
            environment["PKG_CONFIG_LIBDIR"] = pkgconfig_dirs
            environment.pop("LIBRARY_PATH", None)
            excluded_prefixes = [
                value.rstrip("/")
                for value in (
                    environment.get("SNUGPY_CONDA_PREFIX"),
                    environment.get("CONDA_PREFIX"),
                )
                if value
            ]
            library_paths = [
                entry
                for entry in environment.get("LD_LIBRARY_PATH", "").split(":")
                if entry
                and not any(
                    entry == root or entry.startswith(f"{root}/")
                    for root in excluded_prefixes
                )
            ]
            if library_paths:
                environment["LD_LIBRARY_PATH"] = ":".join(library_paths)
            else:
                environment.pop("LD_LIBRARY_PATH", None)
        elif prefix:
            include_dir = f"{prefix.rstrip('/')}/include"
            lib_dir = f"{prefix.rstrip('/')}/lib"
            pkgconfig_dir = f"{lib_dir}/pkgconfig"
            _append_flag(environment, "CPPFLAGS", f"-I{include_dir}")
            _append_flag(
                environment,
                "LDFLAGS",
                f"-L{lib_dir} -Wl,-rpath-link,{lib_dir}",
            )
            environment["PKG_CONFIG_PATH"] = pkgconfig_dir
            environment["PKG_CONFIG_LIBDIR"] = pkgconfig_dir
            environment["LIBRARY_PATH"] = lib_dir
            existing_library_path = environment.get("LD_LIBRARY_PATH", "").strip()
            library_paths = [lib_dir]
            if existing_library_path:
                library_paths.append(existing_library_path)
            environment["LD_LIBRARY_PATH"] = ":".join(library_paths)
        return environment


def load_profiles(path: Path) -> dict[str, ProfileSpec]:
    """Load and validate profiles.toml."""

    with path.open("rb") as handle:
        data = tomllib.load(handle)
    if data.get("schema_version") != 1:
        raise ProfileError(f"{path}: unsupported schema_version")
    raw_profiles = data.get("profiles")
    if not isinstance(raw_profiles, dict) or not raw_profiles:
        raise ProfileError(f"{path}: no profiles defined")

    profiles: dict[str, ProfileSpec] = {}
    for name, raw in raw_profiles.items():
        if not isinstance(raw, dict):
            raise ProfileError(f"{path}: profile {name!r} is not a table")
        try:
            configure = raw["configure"]
            profile = ProfileSpec(
                name=name,
                description=str(raw["description"]),
                cc=str(raw["cc"]),
                cxx=str(raw["cxx"]),
                configure=tuple(str(item) for item in configure),
                cflags=str(raw.get("cflags", "")),
                cppflags=str(raw.get("cppflags", "")),
                cxxflags=str(raw.get("cxxflags", "")),
                ldflags=str(raw.get("ldflags", "")),
                experimental=bool(raw.get("experimental", False)),
                external_libs=str(raw.get("external_libs", "conda")),
            )
        except (KeyError, TypeError) as error:
            raise ProfileError(f"{path}: invalid profile {name!r}: {error}") from error
        if not all(flag.startswith("-") for flag in profile.configure):
            raise ProfileError(
                f"{path}: profile {name!r} has a malformed configure flag"
            )
        if profile.external_libs not in {"conda", "system"}:
            raise ProfileError(
                f"{path}: profile {name!r} has an invalid external_libs value"
            )
        profiles[name] = profile
    return profiles


def resolve_profile(profiles: dict[str, ProfileSpec], name: str) -> ProfileSpec:
    """Return a profile by exact name."""

    try:
        return profiles[name]
    except KeyError as error:
        available = ", ".join(sorted(profiles))
        raise ProfileError(
            f"unknown profile {name!r}; expected one of: {available}"
        ) from error
