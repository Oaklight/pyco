#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOVE_RESULTS=0
REMOVE_SOURCES=0

for argument in "$@"; do
	case "${argument}" in
	--results)
		REMOVE_RESULTS=1
		;;
	--sources)
		REMOVE_SOURCES=1
		;;
	-h | --help)
		cat <<'EOF'
Usage: scripts/clean.sh [--results] [--sources]

Removes generated work, out, and dist trees.
  --results  also remove results/
  --sources  also remove downloaded sources/
EOF
		exit 0
		;;
	*)
		echo "unknown argument: ${argument}" >&2
		exit 2
		;;
	esac
done

python3 - "${ROOT_DIR}" "${REMOVE_RESULTS}" "${REMOVE_SOURCES}" <<'PY'
import shutil
import sys
from pathlib import Path

root = Path(sys.argv[1])
remove_results = sys.argv[2] == "1"
remove_sources = sys.argv[3] == "1"
names = ["work", "out", "dist"]
if remove_results:
    names.append("results")
if remove_sources:
    names.append("sources")
for name in names:
    path = root / name
    if path.exists():
        print(f"removing {path}")
        shutil.rmtree(path)
PY
