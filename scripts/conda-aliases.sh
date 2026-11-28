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

# Conda compiler packages use target-prefixed names. SnugPy profiles call the
# canonical names, so provide stable aliases inside the environment.
if [[ "$(uname -s)" == "Linux" ]]; then
	case "$(uname -m)" in
	aarch64 | arm64) target_prefix="aarch64-conda-linux-gnu" ;;
	*) target_prefix="x86_64-conda-linux-gnu" ;;
	esac
	link_tool "${target_prefix}-gcc" gcc
	link_tool "${target_prefix}-gcc" cc
	link_tool "${target_prefix}-g++" g++
	link_tool "${target_prefix}-g++" c++

	for tool in ld readelf ar ranlib nm objdump strip objcopy addr2line size strings; do
		link_tool "${target_prefix}-${tool}" "${tool}"
	done
fi

for command_name in gcc g++ cc c++ ld readelf strip time hyperfine clang clang++; do
	if [[ ! -e "${PREFIX}/bin/${command_name}" ]] && ! command -v "${command_name}" >/dev/null 2>&1; then
		echo "warning: ${command_name} is still unavailable in ${PREFIX}" >&2
	fi
done
