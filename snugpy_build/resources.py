"""Locate configuration files for source and installed layouts."""

from __future__ import annotations

import sys
from pathlib import Path

from .util import SnugPyError


class ResourceError(SnugPyError):
    """Raised when packaged configuration cannot be found."""


def config_dir(root: Path | None = None) -> Path:
    """Return the directory that contains SnugPy TOML configuration.

    Args:
        root: Optional workspace root to search first.

    Returns:
        The first directory that contains ``versions.toml``.

    Raises:
        ResourceError: If no configuration directory exists.
    """

    candidates: list[Path] = []
    if root is not None:
        candidates.append(root / "configs")
    candidates.append(Path(__file__).resolve().parents[1] / "configs")
    candidates.append(Path(sys.prefix) / "share" / "snugpy" / "configs")

    searched = ", ".join(str(candidate) for candidate in candidates)
    for candidate in candidates:
        if (candidate / "versions.toml").is_file():
            return candidate.resolve()
    raise ResourceError(f"SnugPy configuration not found; searched: {searched}")
