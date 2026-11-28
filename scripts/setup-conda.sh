#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PREFIX="${1:-${SNUGPY_CONDA_PREFIX:-}}"
USE_LOCK="${SNUGPY_CONDA_USE_LOCK:-1}"
ENVIRONMENT_FILE="${ROOT_DIR}/environment.yml"
LOCK_FILE=""

case "$(uname -s)-$(uname -m)" in
Linux-x86_64)
	LOCK_FILE="${ROOT_DIR}/conda-linux-64.lock"
	;;
Linux-aarch64 | Linux-arm64)
	ENVIRONMENT_FILE="${ROOT_DIR}/environment-linux-aarch64.yml"
	LOCK_FILE="${ROOT_DIR}/conda-linux-aarch64.lock"
	;;
Darwin-arm64)
	ENVIRONMENT_FILE="${ROOT_DIR}/environment-macos.yml"
	LOCK_FILE="${ROOT_DIR}/conda-osx-arm64.lock"
	;;
Darwin-x86_64)
	ENVIRONMENT_FILE="${ROOT_DIR}/environment-macos.yml"
	LOCK_FILE="${ROOT_DIR}/conda-osx-64.lock"
	;;
MINGW* | MSYS* | CYGWIN*)
	ENVIRONMENT_FILE="${ROOT_DIR}/environment.yml"
	LOCK_FILE="${ROOT_DIR}/conda-win-64.lock"
	;;
esac

if [[ -z "${PREFIX}" ]]; then
	if [[ -d "${HOME}/ml_lab" ]]; then
		PREFIX="${HOME}/ml_lab/envs/snugpy"
	else
		PREFIX="${ROOT_DIR}/.conda-env"
	fi
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

mkdir -p "$(dirname "${PREFIX}")"

read_environment_packages() {
	mapfile -t packages < <(
		awk '
      /^dependencies:/ { in_deps = 1; next }
      /^[^[:space:]-]/ { in_deps = 0 }
      in_deps && /^[[:space:]]+- / {
        sub(/^[[:space:]]+- /, "")
        print
      }
    ' "${ENVIRONMENT_FILE}"
	)
	if [[ "${#packages[@]}" -eq 0 ]]; then
		echo "no dependencies parsed from ${ENVIRONMENT_FILE}" >&2
		exit 1
	fi
}

create_from_environment_yml() {
	read_environment_packages
	echo "creating conda environment at ${PREFIX} from ${ENVIRONMENT_FILE}"
	"${CONDA_BIN}" create --yes --prefix "${PREFIX}" \
		--override-channels -c conda-forge "${packages[@]}"
}

if [[ -f "${PREFIX}/conda-meta/history" ]]; then
	read_environment_packages
	echo "updating conda environment at ${PREFIX}"
	"${CONDA_BIN}" install --yes --prefix "${PREFIX}" \
		--override-channels -c conda-forge "${packages[@]}"
elif [[ "${USE_LOCK}" == "1" && -n "${LOCK_FILE}" && -f "${LOCK_FILE}" ]]; then
	echo "creating conda environment at ${PREFIX} from ${LOCK_FILE}"
	if ! "${CONDA_BIN}" create --yes --prefix "${PREFIX}" --file "${LOCK_FILE}" \
		--override-channels -c conda-forge; then
		echo "lock-file creation failed" >&2
		echo "remove ${PREFIX} and rerun with SNUGPY_CONDA_USE_LOCK=0 to use environment.yml" >&2
		exit 1
	fi
else
	create_from_environment_yml
fi

if [[ "$(uname -s)" == "Linux" ]]; then
	"${ROOT_DIR}/scripts/install-gdbm-compat.sh" "${PREFIX}"
fi
"${ROOT_DIR}/scripts/conda-aliases.sh" "${PREFIX}"
echo "conda environment ready: ${PREFIX}"
echo "activate with: source \"$("${CONDA_BIN}" info --base)/etc/profile.d/conda.sh\" && conda activate \"${PREFIX}\""
echo "without activation: export SNUGPY_CONDA_PREFIX=\"${PREFIX}\" && export PATH=\"${PREFIX}/bin:\${PATH}\""
