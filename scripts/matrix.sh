#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${VERSION:-3.14}"
TARGET="${TARGET:-linux-x86_64}"
RUNS="${RUNS:-10}"
PROFILES=(baseline size lto static clang-oz)
MODE="--smoke"
NETWORK=""

while [[ $# -gt 0 ]]; do
	case "$1" in
	--version)
		VERSION="$2"
		shift 2
		;;
	--target)
		TARGET="$2"
		shift 2
		;;
	--runs)
		RUNS="$2"
		shift 2
		;;
	--full)
		MODE="--full"
		shift
		;;
	--network)
		NETWORK="--network"
		shift
		;;
	-h | --help)
		cat <<'EOF'
Usage: scripts/matrix.sh [--version 3.14] [--target linux-x86_64] [--runs 10] [--full] [--network]

Runs fetch, build, test, measure, and package for the five initial profiles.
A failed cell does not stop unrelated cells.
EOF
		exit 0
		;;
	*)
		echo "unknown argument: $1" >&2
		exit 2
		;;
	esac
done

status=0
"${ROOT_DIR}/scripts/fetch.sh" "${VERSION}" --zerodep || exit 1

for profile in "${PROFILES[@]}"; do
	echo "=== ${VERSION} ${profile} ${TARGET} ==="
	if ! "${ROOT_DIR}/scripts/build.sh" "${VERSION}" "${profile}" "${TARGET}" --jobs "$(nproc)"; then
		status=1
		continue
	fi
	if ! "${ROOT_DIR}/scripts/test.sh" "${VERSION}" "${profile}" "${TARGET}" "${MODE}" ${NETWORK}; then
		status=1
	fi
	if ! "${ROOT_DIR}/scripts/measure.sh" "${VERSION}" "${profile}" "${TARGET}" --runs "${RUNS}"; then
		status=1
	fi
	if ! "${ROOT_DIR}/scripts/package.sh" "${VERSION}" "${profile}" "${TARGET}"; then
		status=1
	fi
done

"${ROOT_DIR}/scripts/report.sh" || status=1
exit "${status}"
