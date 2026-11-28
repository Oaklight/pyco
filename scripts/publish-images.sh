#!/usr/bin/env bash
set -euo pipefail

usage() {
	cat >&2 <<'EOF'
usage: publish-images.sh VERSION PROFILE TARGET [options]

Build the SnugPy runtime images and optionally push them to a registry.

Options:
  --push                 Push every image after a successful smoke test
  --latest               Also tag and push the scratch runtime-nano image as latest
  --tag TAG              Image tag (default: SNUGPY_RELEASE or package version)
  --namespace NAME       Registry namespace (default: DOCKERHUB_NAMESPACE or oaklight)
  --repository NAME      Repository name (default: DOCKERHUB_REPOSITORY or snugpy)
  -h, --help             Show this help

Environment:
  SNUGPY_RELEASE         Release version used in archive names and the default tag
  GITHUB_SHA             Revision recorded in OCI labels
EOF
	exit 2
}

[[ $# -ge 3 ]] || usage
version=$1
profile=$2
target=$3
shift 3

push=false
latest=false
tag=${SNUGPY_RELEASE:-}
namespace=${DOCKERHUB_NAMESPACE:-oaklight}
repository=${DOCKERHUB_REPOSITORY:-snugpy}

while [[ $# -gt 0 ]]; do
	case "$1" in
	--push)
		push=true
		;;
	--latest)
		latest=true
		;;
	--tag)
		[[ $# -ge 2 ]] || usage
		tag=$2
		shift
		;;
	--namespace)
		[[ $# -ge 2 ]] || usage
		namespace=$2
		shift
		;;
	--repository)
		[[ $# -ge 2 ]] || usage
		repository=$2
		shift
		;;
	-h | --help)
		usage
		;;
	*)
		echo "unknown option: $1" >&2
		usage
		;;
	esac
	shift
done

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"

if [[ -z $tag ]]; then
	tag=$(
		PYTHONPATH="$repo_root" python3 -c \
			'from snugpy_build import __version__; print(__version__)'
	)
fi
[[ -n $tag ]] || {
	echo "image tag is empty" >&2
	exit 2
}
[[ -n $namespace ]] || {
	echo "registry namespace is empty" >&2
	exit 2
}
[[ -n $repository ]] || {
	echo "registry repository is empty" >&2
	exit 2
}

revision=${GITHUB_SHA:-$(git rev-parse HEAD)}
source_url=${OCI_SOURCE:-https://github.com/Oaklight/snugpy}
image_prefix="$namespace/$repository"

labels=(
	--label "org.opencontainers.image.title=SnugPy"
	--label "org.opencontainers.image.description=Compact full-compatibility CPython runtime"
	--label "org.opencontainers.image.url=$source_url"
	--label "org.opencontainers.image.source=$source_url"
	--label "org.opencontainers.image.version=$tag"
	--label "org.opencontainers.image.revision=$revision"
	--label "org.opencontainers.image.licenses=MIT"
)

smoke_code=$(
	cat <<'PY'
import asyncio, bz2, ctypes, hashlib, json, lzma, socket, sqlite3, ssl, uuid, zlib, zoneinfo
assert socket.getservbyname("http", "tcp") == 80
connection = sqlite3.connect(":memory:")
connection.execute("CREATE TABLE items (value INTEGER)")
connection.execute("INSERT INTO items VALUES (1)")
assert connection.execute("SELECT SUM(value) FROM items").fetchone()[0] == 1
connection.close()
assert hashlib.sha256(b"snugpy").hexdigest() == (
    "e64774089588feb2af4ee084af742d89e7fddf7a8791a74f8c3b66782c8c9046"
)
print("runtime-ok")
PY
)

archive_for() {
	local distribution=$1
	local archive
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
	printf '%s\n' "$archive"
}

smoke_image() {
	local ref=$1
	local output
	output=$(
		docker run --rm --platform linux/amd64 --entrypoint python3.14 "$ref" \
			-c "$smoke_code"
	)
	[[ $output == *runtime-ok* ]] || {
		echo "image smoke test failed: $ref" >&2
		exit 1
	}
}

build_image() {
	local distribution=$1
	local dockerfile=$2
	local base=$3
	local ref=$4
	shift 4
	local archive work
	archive=$(archive_for "$distribution")
	work=$(mktemp -d "${TMPDIR:-/tmp}/snugpy-publish-XXXXXX")
	cp "$archive" "$work/runtime.tar.xz"

	local -a build_args=(
		build
		--platform linux/amd64
		--file "$dockerfile"
		--build-arg "BASE=$base"
		--build-arg "ARCHIVE=runtime.tar.xz"
		"${labels[@]}"
		--tag "$ref"
	)
	for argument in "$@"; do
		build_args+=(--build-arg "$argument")
	done
	build_args+=("$work")

	docker "${build_args[@]}" >/dev/null
	rm -rf "$work"

	smoke_image "$ref"
	local bytes
	bytes=$(docker image inspect "$ref" --format '{{.Size}}')
	echo "image=$ref distribution=$distribution image_bytes=$bytes"
}

build_image runtime-nano docker/runtime-scratch.Dockerfile \
	debian:bookworm-slim "$image_prefix:$tag"
build_image runtime docker/runtime-scratch.Dockerfile \
	debian:bookworm-slim "$image_prefix:${tag}-runtime"
build_image runtime docker/runtime-distroless.Dockerfile \
	gcr.io/distroless/cc-debian12:nonroot "$image_prefix:${tag}-distroless"
build_image runtime docker/runtime.Dockerfile \
	debian:bookworm-slim "$image_prefix:${tag}-debian" \
	"PACKAGES=libssl3 libsqlite3-0 netbase"

if [[ $latest == true ]]; then
	docker tag "$image_prefix:$tag" "$image_prefix:latest"
	echo "image=$image_prefix:latest source=$image_prefix:$tag"
fi

if [[ $push == true ]]; then
	docker push "$image_prefix:$tag"
	docker push "$image_prefix:${tag}-runtime"
	docker push "$image_prefix:${tag}-distroless"
	docker push "$image_prefix:${tag}-debian"
	if [[ $latest == true ]]; then
		docker push "$image_prefix:latest"
	fi
fi
