#!/usr/bin/env bash
set -euo pipefail

package=${SNUGPY_PACKAGE:-snugpy}
version=${SNUGPY_VERSION:-}
prefix=${SNUGPY_PREFIX:-${XDG_DATA_HOME:-$HOME/.local/share}/snugpy}
bin_dir=${SNUGPY_BIN_DIR:-${XDG_BIN_HOME:-$HOME/.local/bin}}
python=${SNUGPY_PYTHON:-python3}
force=${SNUGPY_FORCE:-0}
marker=$prefix/.snugpy-install
link=$bin_dir/snugpy

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
case "$bin_dir" in
"" | /) fail "invalid SNUGPY_BIN_DIR: ${bin_dir:-<empty>}" ;;
esac

if [[ $version == latest ]]; then
	version=
fi

command -v "$python" >/dev/null 2>&1 || fail "Python not found: $python"
"$python" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' ||
	fail "Python 3.10 or newer is required"

if [[ -n ${CONDA_PREFIX:-} ]]; then
	say "conda environment detected: $CONDA_PREFIX"
	say "installing into an isolated venv; the conda environment will not be modified"
fi

if [[ -L $prefix ]]; then
	fail "SNUGPY_PREFIX must not be a symlink: $prefix"
fi
if [[ -e $prefix && ! -d $prefix ]]; then
	fail "SNUGPY_PREFIX exists and is not a directory: $prefix"
fi
if [[ -f $marker ]]; then
	[[ -f $prefix/pyvenv.cfg ]] ||
		fail "managed prefix is missing its venv: $prefix; run uninstall.sh first"
elif [[ -e $prefix ]]; then
	if [[ -n $(find "$prefix" -mindepth 1 -maxdepth 1 -print -quit) ]]; then
		fail "refusing to reuse non-empty unmanaged directory: $prefix"
	fi
fi

if [[ -L $link ]]; then
	current=$(readlink "$link")
	if [[ $current != "$prefix/bin/snugpy" && $force != 1 ]]; then
		fail "refusing to replace $link -> $current; set SNUGPY_FORCE=1"
	fi
elif [[ -d $link ]]; then
	fail "$link is a directory"
elif [[ -e $link && $force != 1 ]]; then
	fail "refusing to replace $link; set SNUGPY_FORCE=1"
fi

mkdir -p "$bin_dir"
if [[ -f $prefix/pyvenv.cfg ]]; then
	say "updating existing environment: $prefix"
else
	say "creating environment: $prefix"
	"$python" -m venv "$prefix" ||
		fail "failed to create venv; install the python3-venv package for $python"
fi

"$prefix/bin/python" -m pip --version >/dev/null 2>&1 ||
	fail "the new venv has no pip; install the python3-venv package for $python"
printf 'managed=1\nbin_dir=%s\n' "$bin_dir" >"$marker"

spec=$package
if [[ -n $version ]]; then
	spec="$package==$version"
fi
say "installing $spec"
"$prefix/bin/python" -m pip install --upgrade --disable-pip-version-check --no-input "$spec" ||
	fail "pip install failed: $spec"
ln -sfn "$prefix/bin/snugpy" "$link"

installed_version=$("$prefix/bin/snugpy" --version | awk '{print $2}')
[[ -n $installed_version ]] || fail "installed snugpy did not report a version"
printf 'managed=1\nversion=%s\nbin_dir=%s\n' "$installed_version" "$bin_dir" >"$marker"
"$link" list >/dev/null

say "installed: $link"
case ":$PATH:" in
*":$bin_dir:"*) ;;
*) say "add to PATH: export PATH=\"$bin_dir:\$PATH\"" ;;
esac
resolved=$(command -v snugpy || true)
if [[ -n $resolved && $resolved != "$link" ]]; then
	say "warning: another snugpy is first in PATH: $resolved"
fi
say "uninstall with: curl -fsSL https://raw.githubusercontent.com/Oaklight/snugpy/main/uninstall.sh | bash"
