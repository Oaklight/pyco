#!/usr/bin/env bash
set -euo pipefail

PREFIX="${1:-${SNUGPY_CONDA_PREFIX:-${CONDA_PREFIX:-}}}"

GDBM_VERSION="1.18"
GDBM_URLS=(
	"https://ftp.gnu.org/gnu/gdbm/gdbm-${GDBM_VERSION}.tar.gz"
	"https://ftpmirror.gnu.org/gnu/gdbm/gdbm-${GDBM_VERSION}.tar.gz"
	"https://mirrors.kernel.org/gnu/gdbm/gdbm-${GDBM_VERSION}.tar.gz"
)
GDBM_SHA256="b8822cb4769e2d759c828c06f196614936c88c141c3132b18252fe25c2b635ce"
STAMP="${PREFIX}/.snugpy-gdbm-compat-${GDBM_VERSION}"

if [[ -z "${PREFIX}" ]]; then
	echo "usage: scripts/install-gdbm-compat.sh <conda-prefix>" >&2
	exit 2
fi
if [[ ! -f "${PREFIX}/conda-meta/history" ]]; then
	echo "not a conda environment: ${PREFIX}" >&2
	exit 2
fi
if [[ -f "${STAMP}" && -e "${PREFIX}/lib/libgdbm_compat.so.4" && -f "${PREFIX}/include/ndbm.h" ]]; then
	echo "gdbm ndbm compatibility already installed in ${PREFIX}"
	exit 0
fi

export PATH="${PREFIX}/bin:${PATH}"
CC="${CC:-x86_64-conda-linux-gnu-cc}"
if ! command -v "${CC}" >/dev/null 2>&1; then
	echo "${CC} was not found in ${PREFIX}/bin" >&2
	exit 1
fi

work_dir="$(mktemp -d "${TMPDIR:-/tmp}/snugpy-gdbm-compat.XXXXXX")"
trap 'rm -rf "${work_dir}"' EXIT

archive="${work_dir}/gdbm-${GDBM_VERSION}.tar.gz"
downloaded=0
for url in "${GDBM_URLS[@]}"; do
	echo "fetching gdbm ${GDBM_VERSION} from ${url}"
	if curl --fail --location --silent --show-error \
		--connect-timeout 15 --retry 2 --retry-delay 2 \
		"${url}" -o "${archive}"; then
		downloaded=1
		break
	fi
done
if [[ "${downloaded}" -ne 1 ]]; then
	echo "could not download gdbm ${GDBM_VERSION}" >&2
	exit 1
fi
echo "${GDBM_SHA256}  ${archive}" | sha256sum --check --status
tar -xzf "${archive}" -C "${work_dir}"

build_dir="${work_dir}/gdbm-${GDBM_VERSION}"
echo "building libgdbm_compat against ${PREFIX}"
(
	cd "${build_dir}"
	export CC
	export CFLAGS="-O2 -std=gnu17"
	export CPPFLAGS="-I${PREFIX}/include"
	export LDFLAGS="-L${PREFIX}/lib -Wl,-rpath-link,${PREFIX}/lib"
	./configure \
		--prefix="${PREFIX}" \
		--enable-libgdbm-compat \
		--disable-static \
		--disable-nls \
		--disable-rpath
	make -C src -j"$(nproc)" libgdbm.la
	make -C compat -j"$(nproc)" libgdbm_compat.la
)

install -d "${PREFIX}/lib" "${PREFIX}/include"
install -m 644 "${build_dir}/compat/ndbm.h" "${PREFIX}/include/ndbm.h"
install -m 644 "${build_dir}/compat/dbm.h" "${PREFIX}/include/dbm.h"
cp -P "${build_dir}"/compat/.libs/libgdbm_compat.so* "${PREFIX}/lib/"
printf 'gdbm=%s\nsha256=%s\n' "${GDBM_VERSION}" "${GDBM_SHA256}" >"${STAMP}"
echo "installed libgdbm_compat and ndbm headers in ${PREFIX}"
