#!/usr/bin/env bash
set -euo pipefail

usage() {
	echo "usage: $0 PREFIX [--glibc VERSION] [--openssl VERSION]" >&2
	exit 2
}

[[ $# -ge 1 ]] || usage
root=$1
shift
glibc_allowed=2.34
openssl_allowed=3.0.0
while [[ $# -gt 0 ]]; do
	case "$1" in
	--glibc)
		glibc_allowed=${2:?missing --glibc value}
		shift 2
		;;
	--openssl)
		openssl_allowed=${2:?missing --openssl value}
		shift 2
		;;
	*)
		usage
		;;
	esac
done

[[ -d $root ]] || {
	echo "missing prefix: $root" >&2
	exit 2
}

mapfile -t versions < <(
	find "$root" -type f \( -name '*.so' -o -name 'python3.*' \) -print0 |
		xargs -0 -r objdump -T 2>/dev/null |
		grep -oE '(OPENSSL|GLIBC|GLIBCXX|CXXABI)_[0-9.]+' |
		sort -u
)

fail=0
check_family() {
	local family=$1
	local allowed=$2
	local found max
	found=$(printf '%s\n' "${versions[@]}" | grep -E "^${family}_" | sort -V | tail -1 || true)
	if [[ -z $found ]]; then
		echo "OK: ${family} not referenced"
		return 0
	fi
	max=${found#"${family}_"}
	if [[ $(printf '%s\n%s\n' "$max" "$allowed" | sort -V | tail -1) != "$allowed" ]]; then
		echo "FAIL: ${family} requires ${max}, allowed ${allowed}" >&2
		fail=1
	else
		echo "OK: ${family} max ${max} (allowed ${allowed})"
	fi
}

check_family OPENSSL "$openssl_allowed"
check_family GLIBC "$glibc_allowed"
check_family GLIBCXX 3.4.30
check_family CXXABI 1.3.13

exit "$fail"
