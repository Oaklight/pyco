#!/usr/bin/env bash
set -euo pipefail

prefix=${SNUGPY_PREFIX:-${XDG_DATA_HOME:-$HOME/.local/share}/snugpy}
default_bin_dir=${XDG_BIN_HOME:-$HOME/.local/bin}
explicit_bin_dir=${SNUGPY_BIN_DIR:-}
force=${SNUGPY_FORCE:-0}
marker=$prefix/.snugpy-install

say() { printf '[snugpy] %s\n' "$*"; }
fail() {
	printf '[snugpy] error: %s\n' "$*" >&2
	exit 1
}

case "$force" in
0 | 1) ;;
*) fail "SNUGPY_FORCE must be 0 or 1" ;;
esac

case "$prefix" in
"" | /) fail "invalid SNUGPY_PREFIX: ${prefix:-<empty>}" ;;
esac

if [[ -L $prefix ]]; then
	fail "SNUGPY_PREFIX must not be a symlink: $prefix"
fi

if [[ ! -e $prefix ]]; then
	bin_dir=${explicit_bin_dir:-$default_bin_dir}
	link=$bin_dir/snugpy
	if [[ -L $link && $(readlink "$link") == "$prefix/bin/snugpy" ]]; then
		rm -f -- "$link"
		say "removed orphaned symlink: $link"
	fi
	say "nothing to uninstall: $prefix"
	exit 0
fi

[[ -d $prefix ]] || fail "SNUGPY_PREFIX is not a directory: $prefix"
[[ -f $marker ]] || fail "refusing to remove unmarked directory: $prefix"

managed=
marker_bin_dir=
while IFS='=' read -r key value; do
	case "$key" in
	managed) managed=$value ;;
	bin_dir) marker_bin_dir=$value ;;
	esac
done <"$marker"
[[ $managed == 1 ]] || fail "invalid install marker: $marker"

if [[ -n $explicit_bin_dir ]]; then
	bin_dir=$explicit_bin_dir
	if [[ -n $marker_bin_dir && $explicit_bin_dir != "$marker_bin_dir" ]]; then
		fail "SNUGPY_BIN_DIR differs from the install marker: $marker_bin_dir"
	fi
elif [[ -n $marker_bin_dir ]]; then
	bin_dir=$marker_bin_dir
else
	bin_dir=$default_bin_dir
fi
link=$bin_dir/snugpy

remove_link=0
if [[ -L $link ]]; then
	target=$(readlink "$link")
	if [[ $target == "$prefix/bin/snugpy" ]]; then
		remove_link=1
	elif [[ $force != 1 ]]; then
		fail "refusing to remove unowned symlink: $link -> $target"
	else
		say "warning: leaving unowned symlink: $link -> $target"
	fi
elif [[ -e $link ]]; then
	if [[ $force != 1 ]]; then
		fail "refusing to remove unowned path: $link"
	fi
	say "warning: leaving unowned path: $link"
fi

if [[ $remove_link == 1 ]]; then
	rm -f -- "$link"
	say "removed symlink: $link"
else
	say "no owned symlink to remove: $link"
fi

rm -rf -- "$prefix"
say "removed environment: $prefix"
