# SnugPy

[![CI](https://github.com/Oaklight/snugpy/actions/workflows/ci.yml/badge.svg)](https://github.com/Oaklight/snugpy/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/snugpy.svg)](https://pypi.org/project/snugpy/)
[![Python 版本](https://img.shields.io/pypi/pyversions/snugpy.svg)](https://pypi.org/project/snugpy/)
[![Docker 拉取量](https://img.shields.io/docker/pulls/oaklight/snugpy.svg)](https://hub.docker.com/r/oaklight/snugpy)
[![许可证](https://img.shields.io/github/license/Oaklight/snugpy.svg)](LICENSE)

[English](README_en.md) | 中文

**完整 Python，更小体积。**

SnugPy 构建紧凑、可部署的 Python 运行时，并将每个候选构建与完整 CPython
基线对比测量。它从固定版本的上游 CPython 出发，不重新实现语言，因此兼容性优先。每种
profile 构建都保留标准库、`ensurepip`、`venv`、`idlelib`、`tkinter`、`test`
和可选原生扩展。打包阶段从同一棵裁剪后的目录树生成七个可部署变体：`headless`、
`headed`、`test`、`micro`、`nano`、`runtime` 和 `runtime-nano`。`micro`、
`nano`、`runtime` 和 `runtime-nano` 删除安装器、头文件、文档和开发文件，面向仅运行时
沙盒。

**状态：** 0.1.0。`linux-x86_64` 上的 `static-lean` 已通过完整 CPython 3.14.9
回归测试，以及允许联网的 `zerodep` 测试。其他 profile 仍为实验性。GitHub Actions
是构建、验证和发布路径。

## 起源

SnugPy 与 MicroPython、PocketPy 来自同一个观察：多数部署不需要完整 CPython 源码树或
全部开发产物。与这些项目不同，SnugPy 从 CPython 出发以保留完整兼容性，再删除与部署无关
的部分。后续工作可能更激进地修改解释器；项目名称并不承诺 CPython 保持未修改。

## 版本策略

SnugPy 工具链和 `zerodep` 的兼容下限是 Python 3.10。这**不**表示 SnugPy 必须构建或
分发 CPython 3.10、3.11、3.12 和 3.13。CPython 每个次版本都有不同的 ABI。初始目标
是一个固定的 CPython 3.14 维护版本。未来增加版本时，会为其单独固定源码、构建矩阵和发布
决策；编译产物、安装前缀和配置不会跨版本共享。

## 安装

PyPI 上的 `snugpy` 包是构建与测量工具，不是解释器运行时。解释器运行时请使用发行归档或
Docker 镜像。

### 一行安装

安装器要求 Python 3.10 或更新版本。它会在
`${XDG_DATA_HOME:-$HOME/.local/share}/snugpy` 下创建独立虚拟环境，并在
`${XDG_BIN_HOME:-$HOME/.local/bin}/snugpy` 创建 CLI 链接。

```bash
curl -fsSL https://raw.githubusercontent.com/Oaklight/snugpy/main/install.sh | bash
snugpy --version
```

固定 PyPI 版本：

```bash
curl -fsSL https://raw.githubusercontent.com/Oaklight/snugpy/main/install.sh |
  SNUGPY_VERSION=0.1.0 bash
```

指定其他安装前缀或可执行文件目录：

```bash
curl -fsSL https://raw.githubusercontent.com/Oaklight/snugpy/main/install.sh |
  SNUGPY_PREFIX="$HOME/.local/share/snugpy" \
  SNUGPY_BIN_DIR="$HOME/.local/bin" bash
```

安装器不会复用没有标记的非空目录，也不会替换无关的 `snugpy` 可执行文件。可执行文件冲突
时设置 `SNUGPY_FORCE=1`。设置 `SNUGPY_PYTHON` 可选择用于创建虚拟环境的 Python。重新运行
同一命令可更新受管虚拟环境。

已安装 CLI 读取 wheel 内置配置，并把构建输出写到当前目录。从克隆目录运行时，改用该克隆
的 `configs/`。

### 卸载

```bash
curl -fsSL https://raw.githubusercontent.com/Oaklight/snugpy/main/uninstall.sh | bash
```

使用自定义前缀或可执行文件目录时，给两个脚本传入相同值：

```bash
curl -fsSL https://raw.githubusercontent.com/Oaklight/snugpy/main/uninstall.sh |
  SNUGPY_PREFIX="$HOME/.local/share/snugpy" \
  SNUGPY_BIN_DIR="$HOME/.local/bin" bash
```

卸载器只删除带有效 `.snugpy-install` 标记的虚拟环境，以及指向该环境的符号链接。它不会删除
未标记目录。安装在 conda 环境中的 `pip` 包用 `python -m pip uninstall snugpy` 卸载。

### Conda

PyPI 安装与具体环境无关。`python -m pip` 会安装到当前激活的 Python 环境，包括 conda
环境：

```bash
conda activate myenv
python -m pip install snugpy
```

一行安装器会检测 `CONDA_PREFIX`，报告该环境，并保持 conda 环境不变。希望 `snugpy`
在所有 conda 环境之外可用时使用一行安装器。希望它属于某个 conda 环境时，使用
`python -m pip install snugpy`。

### Docker Hub

运行时镜像发布在
[`oaklight/snugpy`](https://hub.docker.com/r/oaklight/snugpy)，仅支持
`linux/amd64`。

| 标签 | 发行变体 | 基础镜像 | Shell | pip |
| --- | --- | --- | --- | --- |
| `0.1.0`、`latest` | `runtime-nano` | `scratch` | 否 | 否 |
| `0.1.0-runtime` | `runtime` | `scratch` | 否 | 否 |
| `0.1.0-distroless` | `runtime` | distroless `cc-debian12` | 否 | 否 |
| `0.1.0-debian` | `runtime` | Debian 12 slim | 是 | 否 |

`runtime` 保留预装 `site-packages` 和预编译字节码。`runtime-nano` 删除预编译字节码，
因此更小，但首次导入模块时需要编译。scratch 镜像以 UID 65532 运行，不包含 shell 或包
管理器。

```bash
docker run --rm --entrypoint python3.14 oaklight/snugpy:0.1.0 \
  -c 'import ssl, sqlite3; print("runtime-ok")'

docker run --rm --entrypoint python3.14 oaklight/snugpy:0.1.0-debian \
  -c 'import ssl, sqlite3; print("runtime-ok")'
```

发布工作流会构建、冒烟测试并推送这些标签。它不发布多架构 manifest。

## 快速开始

工具链使用 conda-forge 环境，包含 Python 3.12、GCC 16、Clang 23、`lld`、binutils、
`patchelf`、`hyperfine`、GNU `time`、ShellCheck、`go-shfmt`，以及 CPython 可选扩展
所需的库。

```bash
git clone git@github.com:Oaklight/snugpy.git
cd snugpy

# 新前缀存在精确锁文件时，从锁文件创建。
./scripts/setup-conda.sh "$HOME/ml_lab/envs/snugpy"

source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "$HOME/ml_lab/envs/snugpy"

./scripts/check-deps.sh
./scripts/fetch.sh 3.14 --zerodep
./scripts/build.sh 3.14 baseline linux-x86_64
./scripts/test.sh 3.14 baseline linux-x86_64 --smoke
./scripts/package.sh 3.14 baseline linux-x86_64
./scripts/measure.sh 3.14 baseline linux-x86_64 --runs 10
./scripts/report.sh
```

`scripts/setup-conda.sh` 对新前缀优先使用 `conda-linux-64.lock`。锁文件不存在时回退到
`environment.yml`；已有前缀则从 `environment.yml` 更新。设置
`SNUGPY_CONDA_USE_LOCK=0` 可强制使用 YAML 路径。

`scripts/package.sh` 复制一次安装前缀，删除暂存树中 ELF 二进制、可重定位对象和静态归档的
调试符号，然后为每个已配置发行变体写入确定性的 `tar.xz` 归档。原始 `out/` 前缀保留符号
以便调试。请在测量前打包，这样报告能记录归档大小和裁剪后的安装大小。迭代时用
`--distribution headless` 只构建一个变体；重复该参数可选择多个变体。

不激活环境而直接使用它，CI 构建采用这种方式：

```bash
export SNUGPY_CONDA_PREFIX="$HOME/ml_lab/envs/snugpy"
export PATH="$SNUGPY_CONDA_PREFIX/bin:$PATH"
```

`SNUGPY_CONDA_PREFIX` 优先于 `CONDA_PREFIX`。conda 激活会导出优化和加固后的 `CFLAGS`、
`CPPFLAGS` 和 `LDFLAGS`；SnugPy 丢弃这些值，只提供所选 profile 的标志以及 conda 的
include 和库路径。这样 `baseline` 和体积 profile 才可比较。

有意修改环境后重新生成锁文件：

```bash
./scripts/lock-conda.sh "$HOME/ml_lab/envs/snugpy"
```

## Profiles

| Profile | 编译器 | 配置 | 用途 |
| --- | --- | --- | --- |
| `baseline` | GCC | 上游默认优化，共享 libpython | 参考构建 |
| `size` | GCC `-Os` | 共享 libpython | 面向体积的代码生成 |
| `lto` | GCC `-Os` | `--with-lto`，共享 libpython | 体积加链接时优化 |
| `static` | GCC `-Os` | `--disable-shared` | 静态链接 libpython；不是完全静态的系统二进制 |
| `clang-oz` | Clang `-Oz` | 共享 libpython | 激进体积实验 |
| `lean` | Clang `-Oz` | 共享 libpython、`--without-doc-strings`、`--gc-sections` | 最小共享实验；删除 C 文档字符串和 unwind 表 |
| `static-lean` | Clang `-Oz` | `--disable-shared`、`--without-doc-strings`、非 PIE、安全 LLD ICF、Debian 12 系统库 | 最小部署核心；非 PIE 链接、隐藏符号、无 unwind 表、section GC |

`static-lean` 以非 PIE 可执行文件链接解释器。这会删除动态重定位并缩小核心，但会关闭解释器
进程的地址空间布局随机化。仅当容器或 VM 隔离是安全边界时使用它。它也是唯一链接 Debian
12 系统库而非 conda-forge 库的 profile。

合并后的 profile 与发行变体大小见 `docs/version-matrix.md`。外部库和镜像细节见
`docs/runtime-libraries.md`。

每个 profile 有独立的工作树、安装前缀、日志和结果目录。只有完整 CPython 回归测试、
zerodep 测试、ABI 检查、标准库清单检查和测量全部通过后，profile 才具备发布资格。测量会
给出 Pareto 前沿；最小构建不会被自动选中。

## 发行变体

每个 profile 都会生成完整安装前缀。打包阶段从同一棵裁剪后的暂存树生成七个归档，因此
profile 结果和所有变体保持一致。

| 发行变体 | 排除内容 | 冒烟导入 | 用途 |
| --- | --- | --- | --- |
| `headless`（默认） | 测试、仅测试扩展、IDLE、Tk、`config-*/libpython*.a`、`config-*/python.o` | `ssl`、`sqlite3`、`ctypes` | 服务器和通用容器 |
| `headed` | 测试、仅测试扩展、开发归档和对象 | `ssl`、`sqlite3`、`ctypes`、`tkinter` | 需要 Tk/IDLE 的工作站 |
| `test` | 无 | `ssl`、`sqlite3`、`ctypes`、`test` | 兼容性测试和再分发分析 |
| `micro` | 安装器、文档、测试、头文件、开发文件、Tk、curses、dbm、readline | `ssl`、`sqlite3`、`ctypes`、`json`、`asyncio` | 仅标准库的 agent 沙盒 |
| `nano` | `micro` 加 `__pycache__` | `ssl`、`sqlite3`、`ctypes`、`json`、`asyncio` | 最小仅标准库镜像；导入时从源码编译 |
| `runtime` | `micro` 减去安装器，保留 `site-packages` | `ssl`、`sqlite3`、`ctypes`、`json`、`asyncio` | 带预装包的 agent 沙盒 |
| `runtime-nano` | `runtime` 加无 `__pycache__` | `ssl`、`sqlite3`、`ctypes`、`json`、`asyncio` | 带预装包的最小 agent 沙盒 |

`headless`、`headed` 和 `test` 保留 `include/`、`config-*/Makefile`、`ensurepip`、
`venv` 和 `site-packages`，因此 `pip install cffi` 和 `venv` 可用。`micro`、`nano`、
`runtime` 和 `runtime-nano` 仅用于运行时：没有 pip、venv、头文件、构建脚本、
`pydoc_data`，也没有测试或终端 UI 扩展模块。`headless` 和 `headed` 只删除仅测试扩展
（`_test*`、`_ctypes_test`、`xxlimited*`、`xxsubtype`、`_xxtestfuzz`），保留 curses
和 readline。`runtime` 保留 `site-packages`，因此镜像构建时安装的包（numpy、pandas 等）
会保留；只删除 `pip`、`pip-*.dist-info`、`ensurepip` 和 `bin/pip*`。`nano` 和
`runtime-nano` 还删除预编译字节码，因此每个进程首次导入模块时要编译；运行时文件系统只读
时会有少量启动开销。

提供三个运行时 Dockerfile：

- `docker/runtime.Dockerfile`：Debian slim，带 shell 和 apt。
- `docker/runtime-distroless.Dockerfile`：distroless `cc-debian12`，无 shell。
- `docker/runtime-scratch.Dockerfile`：`scratch` 根文件系统，只包含所需 soname、CA
  证书、tzdata、NSS 文件和运行时目录。

CI 中 `runtime-nano` 的 scratch 镜像测得 33,500,721 字节，约 32 MiB。它保留标准库、
HTTPS、SQLite、`ctypes`、压缩模块、时区和 `site-packages`。编辑
`configs/distributions.toml` 可改变变体；默认发行变体是 `headless`。

归档文件名会附加变体名，例如
`snugpy-0.1.0-cpython3.14.9-linux-x86_64-baseline-headless.tar.xz`。包元数据为每个变体保留
一条记录。报告矩阵使用默认发行变体，并分别列出每个变体的安装大小和归档大小。

## 命令

| 命令 | 操作 |
| --- | --- |
| `make conda` | 创建或更新 conda 工具链 |
| `make lock` | 从当前前缀写入 `conda-linux-64.lock` |
| `make check` | 单元测试、`compileall`、ShellCheck 和 `shfmt -d` |
| `make fetch` | 校验并解压固定版本的 CPython 和 zerodep 源码 |
| `make build PROFILE=size` | 构建一个隔离 profile |
| `make test PROFILE=size` | 运行冒烟和 ABI 检查 |
| `make test-full PROFILE=size` | 运行完整 CPython 和 zerodep 检查 |
| `make measure PROFILE=size RUNS=20` | 收集体积、启动、RSS 和工作负载数据 |
| `make package PROFILE=size` | 为所有发行变体创建裁剪归档并冒烟测试 |
| `make package PROFILE=size DISTRIBUTION=headless` | 创建并测试一个发行变体 |
| `make report` | 写入 `results/summary.csv` 和 `results/report.md` |
| `make matrix` | 运行全部七个 profile，不因无关失败停止 |
| `make images PROFILE=static-lean IMAGE_TAG=0.1.0` | 本地构建四个运行时镜像 |
| `make publish-images PROFILE=static-lean IMAGE_TAG=0.1.0` | 构建、冒烟测试并推送镜像和 `latest` |
| `make clean` | 删除 `work/`、`out/` 和 `dist/` |

直接脚本以位置参数接收 `VERSION`、`TARGET` 和 `PROFILE`。使用
`python -m snugpy_build.cli list` 查看当前配置值。

## 固定版本

- CPython `3.14.9`，标签 `v3.14.9`，提交
  `ead82c07db1f111d613926ed1b6667411d768125`，SHA256
  `e02d9ac21cebda6e46435369744a92c65cc7cd8669697694122cf97ffacd1e53`
- zerodep `v2026.11.20`，提交
  `9f872e8d652272c34600b9fda6448fe4fd4436c3`
- 目标 `linux-x86_64`
- conda 链接 profile 使用 conda-forge sysroot glibc `2.34`
- `static-lean` 使用 Debian 12 系统库；测得 `GLIBC_2.35`，允许 `GLIBC_2.36`，
  OpenSSL `3.0`
- 工具链：Python `3.12`、GCC `16`、Clang `23`、`lld`、GNU binutils

CI runner 是 Ubuntu 24.04，但 conda sysroot 是 2.34。`static-lean` 不使用该
sysroot；它在 `debian:bookworm` 中构建并链接 Debian 系统库。任何可移植性或发布声明之前，
都必须用 `scripts/check-abi.sh` 或 `objdump -T` 检查每个产物的实际符号需求。这些归档不是
通用 Linux 发行版。

conda 链接 profile 的原生扩展链接 conda-forge 库，例如 OpenSSL、SQLite 和 `libffi`。
`static-lean` 扩展改为链接 Debian soname。两种情况下，归档都不捆绑这些库。运行解压产物
时要提供匹配的库集合，或在再分发前捆绑所需库。

conda-forge 的 `gdbm` 包缺少 ndbm 兼容库。conda 安装步骤从固定 GDBM `1.18` 源码构建
`libgdbm_compat`，因此 `_dbm` 和 `_gdbm` 都可用。`tests/smoke.py` 验证一次 ndbm 往返。

## 目录结构

```text
configs/        immutable versions, targets, profiles, release decisions
snugpy_build/     CLI, source verification, build, validation, metrics, packaging
scripts/        shell entry points and conda environment setup
tests/          unit tests, runtime smoke test, C ABI smoke module
benchmarks/     CPU and I/O workloads
patches/        exceptional common and version-specific patches
sources/        verified upstream source trees (ignored)
work/           per-cell generated build trees (ignored)
out/            per-cell install prefixes (ignored)
dist/           distribution archives (ignored)
results/        metadata per cell; summary.csv and report.md are tracked
install.sh      one-line installer for the PyPI CLI
uninstall.sh    uninstaller for the managed venv
```

## CI

`.github/workflows/ci.yml` 先运行单元检查，再将六个 conda 链接 profile 作为独立矩阵任务
构建，使用 `fail-fast: false`。每个任务从 `conda-linux-64.lock` 创建 conda 环境，
运行 fetch、build、冒烟测试、打包和测量，并上传 JSON 结果和归档。单独的 `static-lean`
任务在 `debian:bookworm` 中运行，链接 Debian 系统库并执行 ABI 检查。依赖任务测量 Debian
slim、distroless、scratch `runtime` 和 scratch `runtime-nano` 镜像。汇总任务下载所有
profile 结果并重新生成报告。

`.github/workflows/benchmark.yml` 是手动完整回归和重复测量路径。它运行完整 CPython 测试
套件和允许联网的 zerodep 测试，然后打包并测量一个选定 profile。

`.github/workflows/release.yml` 是发布路径。它校验源码版本和已批准的发布 profile，构建
并完整测试 `static-lean`，发布 Python 包到 PyPI，推送 Docker Hub 镜像，并用归档、校验和
及报告创建 GitHub Release。运行前需设置仓库密钥 `DOCKERHUB_USERNAME`、
`DOCKERHUB_TOKEN` 和 `PYPI_API_TOKEN`。

## 文档

- `README_en.md`：英文 README
- `README_zh.md`：中文 README
- `CHANGELOG.md`：发布历史和已知限制
- `docs/version-matrix.md`：Python 版本、profile、发行变体和大小
- `docs/runtime-libraries.md`：ABI 检查、库清单和镜像大小

## 许可证

SnugPy 使用 MIT 许可证，见 `LICENSE`。

发行归档还包含源自 CPython 的文件。CPython 保留自己的 PSF License Agreement，每个归档都
在 `licenses/CPython-PSF-LICENSE.txt` 中包含该协议。第三方组件列在
`THIRD_PARTY_LICENSES.md`。
