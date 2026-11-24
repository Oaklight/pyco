#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${ROOT_DIR}${PYTHONPATH:+:${PYTHONPATH}}"
TARGET="${TARGET:-linux-x86_64}"
INSTALL=0

while [[ $# -gt 0 ]]; do
	case "$1" in
	--install-ubuntu)
		INSTALL=1
		shift
		;;
	--target)
		TARGET="${2:?--target requires a value}"
		shift 2
		;;
	-h | --help)
		cat <<'EOF'
Usage: scripts/check-deps.sh [--install-ubuntu] [--target linux-x86_64]

Checks required build tools and prints their versions.
EOF
		exit 0
		;;
	*)
		echo "unknown argument: $1" >&2
		exit 2
		;;
	esac
done

if [[ "${INSTALL}" -eq 1 ]]; then
	command -v apt-get >/dev/null 2>&1 || {
		echo "apt-get is required for --install-ubuntu" >&2
		exit 1
	}
	mapfile -t packages < <(python3 -m pyco_build.cli deps --target "${TARGET}")
	if [[ "${#packages[@]}" -eq 0 ]]; then
		echo "no packages configured for target ${TARGET}" >&2
		exit 1
	fi
	if [[ "$(id -u)" -eq 0 ]]; then
		apt-get update
		DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${packages[@]}"
	else
		command -v sudo >/dev/null 2>&1 || {
			echo "sudo is required to install packages as a non-root user" >&2
			exit 1
		}
		sudo apt-get update
		sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${packages[@]}"
	fi
fi

required=(git python3 make patch readelf ldd strip file tar gzip cc c++ pkg-config time)
optional=(clang clang++ hyperfine patchelf shellcheck shfmt)
missing=()

for command_name in "${required[@]}"; do
	if ! command -v "${command_name}" >/dev/null 2>&1; then
		missing+=("${command_name}")
	fi
done

for command_name in "${optional[@]}"; do
	if ! command -v "${command_name}" >/dev/null 2>&1; then
		echo "warning: optional command missing: ${command_name}" >&2
	fi
done

if [[ "${#missing[@]}" -ne 0 ]]; then
	echo "missing required tools: ${missing[*]}" >&2
	echo "run scripts/check-deps.sh --install-ubuntu on Ubuntu" >&2
	exit 1
fi

echo "python3: $(python3 --version 2>&1)"
echo "cc: $(cc --version 2>&1 | head -1)"
echo "c++: $(c++ --version 2>&1 | head -1)"
echo "make: $(make --version 2>&1 | head -1)"
echo "ld: $(ld --version 2>&1 | head -1)"
echo "libc: $(ldd --version 2>&1 | head -1)"
echo "target: ${TARGET}"
