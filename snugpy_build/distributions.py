"""Distribution variants for packaged CPython trees."""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

from .util import SnugPyError

DEFAULT_DISTRIBUTION = "headless"


class DistributionError(SnugPyError):
    """Raised for invalid distribution configuration."""


@dataclass(frozen=True)
class DistributionVariant:
    """One deployable subset of an installed CPython tree."""

    name: str
    description: str
    exclude: tuple[str, ...]
    smoke_imports: tuple[str, ...]

    def matches_exclude(self, relative: str) -> bool:
        """Return whether a prefix-relative path belongs to an excluded tree.

        Patterns match a path component by component. A pattern that matches a
        directory therefore excludes every file below that directory.
        """

        parts = relative.split("/")
        for pattern in self.exclude:
            for index in range(1, len(parts) + 1):
                if fnmatchcase("/".join(parts[:index]), pattern):
                    return True
        return False


@dataclass(frozen=True)
class DistributionSet:
    """All configured distribution variants."""

    default: str
    variants: tuple[DistributionVariant, ...]

    def get(self, name: str) -> DistributionVariant:
        for variant in self.variants:
            if variant.name == name:
                return variant
        available = ", ".join(variant.name for variant in self.variants)
        raise DistributionError(
            f"unknown distribution {name!r}; expected one of: {available}"
        )

    def default_variant(self) -> DistributionVariant:
        return self.get(self.default)


def _require_table(data: object, name: str) -> dict[str, object]:
    if not isinstance(data, dict):
        raise DistributionError(f"{name} must be a table")
    return data


def load_distributions(root: Path) -> DistributionSet:
    """Load distribution variants from configs/distributions.toml."""

    path = root / "configs" / "distributions.toml"
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    if data.get("schema_version") != 1:
        raise DistributionError(f"{path}: unsupported schema_version")
    default = str(data.get("default", ""))
    raw_variants = _require_table(data.get("variants"), f"{path}: variants")
    variants: list[DistributionVariant] = []
    for name, raw_value in raw_variants.items():
        raw = _require_table(raw_value, f"{path}: variants.{name}")
        exclude = raw.get("exclude", [])
        smoke_imports = raw.get("smoke_imports", ["ssl", "sqlite3", "ctypes"])
        if not isinstance(exclude, list):
            raise DistributionError(f"{path}: variants.{name}.exclude must be a list")
        if not isinstance(smoke_imports, list):
            raise DistributionError(
                f"{path}: variants.{name}.smoke_imports must be a list"
            )
        patterns: list[str] = []
        for pattern in exclude:
            text = str(pattern).replace("\\", "/").strip()
            while text.startswith("./"):
                text = text[2:]
            text = text.rstrip("/")
            if not text:
                raise DistributionError(
                    f"{path}: variants.{name}.exclude must not contain empty paths"
                )
            if text.startswith("/") or ".." in Path(text).parts:
                raise DistributionError(
                    f"{path}: variants.{name}.exclude must stay inside the prefix"
                )
            patterns.append(text)
        variants.append(
            DistributionVariant(
                name=name,
                description=str(raw.get("description", "")),
                exclude=tuple(patterns),
                smoke_imports=tuple(str(item) for item in smoke_imports),
            )
        )
    if not variants:
        raise DistributionError(f"{path}: no distributions configured")
    names = {variant.name for variant in variants}
    if default not in names:
        raise DistributionError(f"{path}: default distribution {default!r} is missing")
    return DistributionSet(default=default, variants=tuple(variants))
