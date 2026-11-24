#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PREFIX="${1:-${PYCO_CONDA_PREFIX:-}}"
LOCK_FILE="${ROOT_DIR}/conda-linux-64.lock"
USE_LOCK="${PYCO_CONDA_USE_LOCK:-1}"

if [[ -z "${PREFIX}" ]]; then
	if [[ -d "${HOME}/ml_lab" ]]; then
		PREFIX="${HOME}/ml_lab/envs/pyco"
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
    ' "${ROOT_DIR}/environment.yml"
	)
	if [[ "${#packages[@]}" -eq 0 ]]; then
		echo "no dependencies parsed from ${ROOT_DIR}/environment.yml" >&2
		exit 1
	fi
}

create_from_environment_yml() {
	read_environment_packages
	echo "creating conda environment at ${PREFIX} from environment.yml"
	"${CONDA_BIN}" create --yes --prefix "${PREFIX}" \
		--override-channels -c conda-forge "${packages[@]}"
}

if [[ -f "${PREFIX}/conda-meta/history" ]]; then
	read_environment_packages
	echo "updating conda environment at ${PREFIX}"
	"${CONDA_BIN}" install --yes --prefix "${PREFIX}" \
		--override-channels -c conda-forge "${packages[@]}"
elif [[ "${USE_LOCK}" == "1" && -f "${LOCK_FILE}" ]]; then
	echo "creating conda environment at ${PREFIX} from ${LOCK_FILE}"
	if ! "${CONDA_BIN}" create --yes --prefix "${PREFIX}" --file "${LOCK_FILE}" \
		--override-channels -c conda-forge; then
		echo "lock-file creation failed" >&2
		echo "remove ${PREFIX} and rerun with PYCO_CONDA_USE_LOCK=0 to use environment.yml" >&2
		exit 1
	fi
else
	create_from_environment_yml
fi

"${ROOT_DIR}/scripts/conda-aliases.sh" "${PREFIX}"
echo "conda environment ready: ${PREFIX}"
echo "activate with: source \"$("${CONDA_BIN}" info --base)/etc/profile.d/conda.sh\" && conda activate \"${PREFIX}\""
echo "without activation: export PYCO_CONDA_PREFIX=\"${PREFIX}\" && export PATH=\"${PREFIX}/bin:\${PATH}\""
