#!/usr/bin/env bash
set -euo pipefail

PREFIX="${1:-${CONDA_PREFIX:-}}"
if [[ -z "${PREFIX}" || ! -d "${PREFIX}" ]]; then
	echo "usage: scripts/conda-aliases.sh <conda-prefix>" >&2
	exit 2
fi

link_tool() {
	local target="$1"
	local alias_name="$2"
	if [[ -x "${PREFIX}/bin/${target}" && ! -e "${PREFIX}/bin/${alias_name}" ]]; then
		ln -s "${target}" "${PREFIX}/bin/${alias_name}"
	fi
}

# Conda compiler packages use target-prefixed names. Pyco profiles call the
# canonical names, so provide stable aliases inside the environment.
link_tool x86_64-conda-linux-gnu-gcc gcc
link_tool x86_64-conda-linux-gnu-gcc cc
link_tool x86_64-conda-linux-gnu-g++ g++
link_tool x86_64-conda-linux-gnu-g++ c++

for tool in ld readelf ar ranlib nm objdump strip objcopy addr2line size strings; do
	link_tool "x86_64-conda-linux-gnu-${tool}" "${tool}"
done

for command_name in gcc g++ cc c++ ld readelf strip time hyperfine clang clang++; do
	if [[ ! -e "${PREFIX}/bin/${command_name}" ]] && ! command -v "${command_name}" >/dev/null 2>&1; then
		echo "warning: ${command_name} is still unavailable in ${PREFIX}" >&2
	fi
done
