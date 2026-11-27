# Third-party licenses

SnugPy is licensed under the MIT License. See `LICENSE`.

A SnugPy distribution archive contains CPython-derived files, the CPython
standard library, and extension modules. Those files keep their original
licenses. This file lists the components that are included in an archive or
that the extension modules link at runtime.

## Included in every archive

| Component | License | Notes |
| --- | --- | --- |
| CPython | PSF License Agreement | `licenses/CPython-PSF-LICENSE.txt` |
| pip | MIT | Bundled wheel used by `ensurepip` |
| setuptools | MIT | Bundled wheel used by `ensurepip` |
| CPython vendored modules | See CPython inventory | Expat, zlib, mpdecimal, and others; see `licenses/CPython-third-party-licenses.rst` |

The packaging step copies the pinned CPython `LICENSE` and its `Doc/license.rst`
inventory into the archive. Those files are authoritative for the CPython
version in that archive.

## Linked at runtime

Extension modules in the conda-linked profiles build against conda-forge
libraries. `static-lean` builds against Debian 12 system libraries. In both
cases the archive does not contain those shared libraries; the host or
container image must provide them.

| Component | License | Used by |
| --- | --- | --- |
| OpenSSL | Apache-2.0 | `_ssl`, `_hashlib` |
| SQLite | Public domain | `_sqlite3` |
| libffi | MIT | `_ctypes` |
| zlib | zlib license | `zlib`, `binascii`, OpenSSL |
| bzip2 | bzip2 license | `_bz2` |
| XZ Utils (liblzma) | 0BSD | `_lzma` |
| Zstandard | BSD-3-Clause | `_zstd`, OpenSSL |
| Brotli | MIT | conda OpenSSL builds only; not used by Debian 12 |
| libuuid | BSD-3-Clause | `_uuid` |
| ncurses | X11-style | `_curses`, `readline` |
| GNU Readline | GPL-3.0-or-later | `readline` |
| GDBM | GPL-3.0-or-later | `_gdbm` |
| Tcl/Tk | BSD-style | `_tkinter` (headed variant only) |

The Debian packages behind the `static-lean` `runtime` inventory are `libssl3`,
`libsqlite3-0`, `libffi8`, `zlib1g`, `libbz2-1.0`, `liblzma5`, `libzstd1`, and
`libuuid1`. Debian's OpenSSL links zstd but not Brotli. The `headless` and
`headed` variants can additionally need `libncursesw6`, `libreadline8`, and
`libgdbm6`.

## Copyleft runtime libraries

`readline` and `_gdbm` link against GPL-3.0-or-later libraries that are not
included in a SnugPy archive. If you redistribute a runtime image that contains
those libraries, review the GPL obligations for that image. Building with
libedit (`--with-readline=editline`) avoids the GNU Readline dependency.
