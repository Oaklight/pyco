#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PREFIX="${1:-${SNUGPY_CONDA_PREFIX:-${CONDA_PREFIX:-}}}"
LOCK_FILE=""
case "$(uname -s)-$(uname -m)" in
Linux-x86_64) LOCK_FILE="${ROOT_DIR}/conda-linux-64.lock" ;;
Linux-aarch64 | Linux-arm64) LOCK_FILE="${ROOT_DIR}/conda-linux-aarch64.lock" ;;
Darwin-arm64) LOCK_FILE="${ROOT_DIR}/conda-osx-arm64.lock" ;;
Darwin-x86_64) LOCK_FILE="${ROOT_DIR}/conda-osx-64.lock" ;;
MINGW* | MSYS* | CYGWIN*) LOCK_FILE="${ROOT_DIR}/conda-win-64.lock" ;;
esac
if [[ -z "${LOCK_FILE}" ]]; then
	echo "unsupported platform for conda lock generation: $(uname -s)-$(uname -m)" >&2
	exit 2
fi

if [[ -z "${PREFIX}" || ! -f "${PREFIX}/conda-meta/history" ]]; then
	echo "usage: scripts/lock-conda.sh <conda-prefix>" >&2
	echo "the prefix must be an existing conda environment" >&2
	exit 2
fi

CONDA_BIN="${CONDA_EXE:-}"
if [[ -z "${CONDA_BIN}" ]]; then
	CONDA_BIN="$(command -v conda || true)"
fi
if [[ -z "${CONDA_BIN}" ]]; then
	for candidate in \
		"${HOME}/miniconda3/bin/conda" \
		"${HOME}/miniforge3/bin/conda" \
		"${HOME}/mambaforge/bin/conda" \
		"${HOME}/anaconda3/bin/conda"; do
		if [[ -x "${candidate}" ]]; then
			CONDA_BIN="${candidate}"
			break
		fi
	done
fi
if [[ -z "${CONDA_BIN}" ]]; then
	echo "conda was not found; install Miniforge or set CONDA_EXE" >&2
	exit 1
fi

"${CONDA_BIN}" list --explicit --prefix "${PREFIX}" >"${LOCK_FILE}"
echo "wrote ${LOCK_FILE} from ${PREFIX}"
