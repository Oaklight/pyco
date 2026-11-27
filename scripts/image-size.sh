#!/usr/bin/env bash
set -euo pipefail

usage() {
	echo "usage: $0 VERSION PROFILE TARGET [BASE_IMAGE] [DISTRIBUTION]" >&2
	exit 2
}

[[ $# -ge 3 ]] || usage
version=$1
profile=$2
target=$3
base_image=${4:-debian:bookworm-slim}
distribution=${5:-runtime}

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"

archive=$(
	PYTHONPATH="$repo_root" python3 -m snugpy_build.cli paths \
		"$version" "$profile" "$target" |
		awk -F= -v name="$distribution" '$1 == "archive[" name "]" {print $2}'
)
[[ -n $archive ]] || {
	echo "no archive configured for distribution: $distribution" >&2
	exit 2
}
[[ -f $archive ]] || {
	echo "archive not found: $archive; run package first" >&2
	exit 2
}

work=$(mktemp -d "${TMPDIR:-/tmp}/snugpy-image-XXXXXX")
trap 'rm -rf "$work"' EXIT
cp "$archive" "$work/runtime.tar.xz"

tag="snugpy-image-${profile}-${distribution}-$(date +%s)-$$"
packages=${IMAGE_PACKAGES:-libssl3 libsqlite3-0}
docker build -q \
	-f "$repo_root/docker/runtime.Dockerfile" \
	--build-arg BASE="$base_image" \
	--build-arg PACKAGES="$packages" \
	--build-arg ARCHIVE=runtime.tar.xz \
	-t "$tag" \
	"$work" >/dev/null

bytes=$(docker image inspect "$tag" --format '{{.Size}}')
docker run --rm "$tag" python3.14 -c \
	"import ssl, sqlite3, ctypes, json, asyncio; print('runtime-ok')"

echo "image=$tag"
echo "base=$base_image"
echo "distribution=$distribution"
echo "image_bytes=$bytes"
