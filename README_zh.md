# SnugPy

[![CI](https://github.com/Oaklight/snugpy/actions/workflows/ci.yml/badge.svg)](https://github.com/Oaklight/snugpy/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/snugpy.svg)](https://pypi.org/project/snugpy/)
[![Python 版本](https://img.shields.io/pypi/pyversions/snugpy.svg)](https://pypi.org/project/snugpy/)
[![Docker 拉取量](https://img.shields.io/docker/pulls/oaklight/snugpy.svg)](https://hub.docker.com/r/oaklight/snugpy)
[![许可证](https://img.shields.io/github/license/Oaklight/snugpy.svg)](LICENSE)

[English](README_en.md) | 中文

**完整 Python，更小体积。**

SnugPy 将 CPython 变成可部署运行时。它从固定版本的 CPython 3.14.9 出发，保留语言、
核心标准库和 CPython C 扩展 ABI，再删除仅部署时不需要的文件并缩小解释器。最小的运行时
变体 `runtime-nano` 安装后为 16.4 MiB，压缩后为 3.5 MiB。同一 `static-lean` 流水线生成的
全量 CPython `test` 构建安装后为 242.3 MiB，压缩后为 26.0 MiB。

需要完整 CPython 兼容性的 agent 沙盒或 Linux 服务使用 SnugPy。只需小型 Python 子集时
使用 MicroPython 或 PocketPy。需要无默认文件系统和网络、低延迟的严格沙箱时使用 Monty。

**状态：** 0.1.0。`linux-x86_64` 上的 `static-lean` 已通过完整 CPython 3.14.9
回归测试，以及允许联网的 `zerodep` 测试。其他 profile 仍为实验性。GitHub Actions
是构建、验证和发布路径。原生 CI 任务还会构建 `linux-arm64`、`macos-arm64`、
`macos-x86_64` 和 `windows-x86_64`；工作流通过前，这些产物不进入发布选择。

## 概览

| 属性 | SnugPy 0.1.0 |
| --- | --- |
| 实现 | CPython 3.14.9 |
| 兼容性 | 完整 CPython 语言与 C 扩展 ABI |
| 最小运行时 | `runtime-nano`：安装 16.4 MiB，归档 3.5 MiB |
| 相对完整 CPython | 安装体积减少 93.2%，归档减少 86.4% |
| Agent 沙盒镜像 | 31.95 MiB `scratch` 镜像 |
| 发布目标 | `linux-x86_64` |
| 原生构建目标 | `linux-arm64`、`macos-arm64`、`macos-x86_64`、`windows-x86_64` |

## 与其他实现对比

下表使用本仓库的测量产物，以及 2026-11-28 在 `linux-x86_64` 上构建的对比项目。
体积没有按功能集归一化。

| 运行时 | 实现方式 | 兼容性 | 部署体积 | 主要取舍 |
| --- | --- | --- | --- | --- |
| CPython 3.14.9（完整 `test` 构建） | 参考 C 实现，由 SnugPy 打包 | 完整 CPython 语言、标准库和 C 扩展 ABI | 安装 242.3 MiB / `tar.xz` 26.0 MiB（`test`） | 体积最大 |
| **SnugPy 0.1.0** | **CPython 3.14.9，裁剪并优化** | **完整 CPython 语言和 C 扩展 ABI；运行时变体删除安装器、头文件、测试和 UI 文件** | **安装 16.4 MiB / `tar.xz` 3.5 MiB（`runtime-nano`）；`scratch` 镜像 31.95 MiB** | **发布目标为 Linux x86_64；另有四个原生构建目标；运行时变体没有 pip 和头文件** |
| MicroPython 1.29.0 | 独立 C 实现 | Python 3.4 语法及部分后续特性；标准库子集 | 已 strip 的 Unix 二进制 0.82 MiB | 不是完整 CPython；没有 CPython C 扩展 ABI |
| PocketPy 2.2.0 | 独立 C11 实现 | Python 3 子集 | 已 strip 的 CLI 0.59 MiB | 面向游戏脚本；不是完整 CPython |
| Monty 1.7.0 | 独立 Rust 实现 | 部分 Python 3.14 子集，带沙箱 API | 安装后的二进制 34.7 MiB / wheel 16.3 MiB | 无默认文件系统和网络；能力由宿主提供 |

测量口径：SnugPy 与 CPython 数据来自 `docs/version-matrix.md`；MicroPython 1.29.0 和
PocketPy 2.2.0 从标签源码构建；Monty 1.7.0 使用 PyPI 的 manylinux x86-64 runtime
wheel。MicroPython 和 PocketPy 是单个已 strip 的可执行文件，CPython 与 SnugPy 是安装
目录和压缩归档。

SnugPy 压缩归档仍是 MicroPython 二进制的 4.3 倍、PocketPy 二进制的 6.0 倍。这个差距
来自完整 CPython。SnugPy 的安装体积约为 Monty 1.7.0 安装二进制的 47%，但 Monty 在 VM
层执行资源限制，并且只暴露宿主提供的能力。

## 为什么不直接使用更小的解释器？

MicroPython 和 PocketPy 通过实现 Python 子集，并定义自己的标准库和原生模块 API 来获得
小体积。Monty 为沙箱实现了 Python 子集，能力由宿主提供。部署不需要完整 CPython 时，
这些选择更合适。

SnugPy 保留 CPython 实现。运行时变体保留服务和 agent 使用的核心标准库模块，包括
`ssl`、`sqlite3`、`ctypes`、`json` 和 `asyncio`。`runtime` 系列还保留
`site-packages`，因此镜像构建时安装的 numpy、pandas 等包会保留。原生扩展需要针对
CPython 3.14 构建，并在运行时提供匹配的外部库。

体积缩减来自删除部署不需要的文件：测试、头文件、`config-*`、静态归档、`ensurepip`、
pip、IDLE/Tk、文档、`pydoc_data`，以及 `runtime-nano` 中的 `__pycache__`。它不是通过
重新实现 Python 得到的。

## SnugPy 不做什么

- 它不是新的 Python 实现。语言语义和 C 扩展 ABI 来自 CPython。
- 它不是安全沙箱本身。`static-lean` 是非 PIE；安全边界应使用容器或 VM。
- 它尚未在 `linux-x86_64` 之外发布。Linux ARM64、macOS ARM64、macOS Intel 和
  Windows x86_64 已提供原生 CI 产物，但还不是批准的发布产物。
- 它不是运行时变体中的包安装器。`runtime` 和 `runtime-nano` 保留预装包，但删除 pip 和
  `ensurepip`。

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

## 从源码构建

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
`--distribution runtime-nano` 只构建一个变体；重复该参数可选择多个变体。

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
| `test` | 无 | `ssl`、`sqlite3`、`ctypes`、`test` | 完整 CPython 对比和兼容性测试 |
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
`snugpy-0.1.0-cpython3.14.9-linux-x86_64-static-lean-runtime-nano.tar.xz`。包元数据为每个
变体保留一条记录。报告矩阵使用默认发行变体，并分别列出每个变体的安装大小和归档大小。

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
| `make package PROFILE=size DISTRIBUTION=runtime-nano` | 创建并测试一个发行变体 |
| `make report` | 写入 `results/summary.csv` 和 `results/report.md` |
| `make matrix` | 运行全部七个 profile，不因无关失败停止 |
| `make images PROFILE=static-lean IMAGE_TAG=0.1.0` | 本地构建四个运行时镜像 |
| `make publish-images PROFILE=static-lean IMAGE_TAG=0.1.0` | 构建、冒烟测试并推送镜像和 `latest` |
| `make clean` | 删除 `work/`、`out/` 和 `dist/` |

直接脚本以位置参数接收 `VERSION`、`TARGET` 和 `PROFILE`。使用
`python -m snugpy_build.cli list` 查看当前配置值。

原生构建单元使用相同命令形状：

| 目标 | Runner | Profile | 后端 |
| --- | --- | --- | --- |
| `linux-x86_64` | `ubuntu-24.04` / Debian 12 容器 | `static-lean` | `configure` |
| `linux-arm64` | `ubuntu-24.04-arm` / Debian 12 容器 | `static-lean` | `configure` |
| `macos-arm64` | `macos-15` | `macos-static` | `configure` |
| `macos-x86_64` | `macos-15-intel` | `macos-static` | `configure` |
| `windows-x86_64` | `windows-2025` | `windows-release` | `pcbuild` |

```bash
./scripts/build.sh 3.14 static-lean linux-arm64 --jobs "$(nproc)"
./scripts/build.sh 3.14 macos-static macos-arm64 --jobs "$(sysctl -n hw.logicalcpu)"
python -m snugpy_build.cli build 3.14 windows-release windows-x86_64
```

Docker 可以构建两种 Linux 架构的产物。macOS 需要 Apple SDK 和原生签名工具，
Windows 使用 MSVC `PCbuild`；两者都不是本项目支持的 Docker 构建目标。

## 可移植性与限制

- CPython `3.14.9` 是唯一构建目标，由标签、提交和源码 SHA256 固定。
- `linux-x86_64` 是唯一发布批准目标。原生 CI 构建另外四个目标，但尚未批准发布。
- macOS 归档当前按绝对路径链接 Homebrew 库。在加入依赖捆绑前，只应视为与 runner
  兼容的 CI 产物。
- Windows 产物是 MSVC 构建的 `tar.xz` 目录，不是 `.exe` 安装器。
- `static-lean` 是非 PIE 可执行文件。安全边界必须使用容器或 VM。
- 发行归档不捆绑外部 C 库。运行时需提供文档列出的 soname，或使用镜像。
- 运行时变体没有 pip、`ensurepip`、头文件或构建工具。
- `runtime-nano` 首次导入标准库模块时编译。启动延迟比镜像体积更重要时使用 `runtime`。

conda-forge 的 `gdbm` 包缺少 ndbm 兼容库。conda 安装步骤从固定 GDBM `1.18` 源码构建
`libgdbm_compat`，因此 `_dbm` 和 `_gdbm` 都可用。`tests/smoke.py` 验证一次 ndbm 往返。

conda 链接 profile 的原生扩展链接 conda-forge 库，例如 OpenSSL、SQLite 和 `libffi`。
`static-lean` 扩展改为链接 Debian soname。两种情况下，归档都不捆绑这些库。运行解压产物
时要提供匹配的库集合，或在再分发前捆绑所需库。

任何可移植性或发布声明之前，都必须用 `scripts/check-abi.sh` 或 `objdump -T` 检查每个
产物的实际符号需求。这些归档不是通用 Linux 发行版。

## 版本策略

SnugPy 工具链和 `zerodep` 的兼容下限是 Python 3.10。这**不**表示 SnugPy 必须构建或
分发 CPython 3.10、3.11、3.12 和 3.13。CPython 每个次版本都有不同的 ABI。初始目标
是一个固定的 CPython 3.14 维护版本。未来增加版本时，会为其单独固定源码、构建矩阵和发布
决策；编译产物、安装前缀和配置不会跨版本共享。

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

`.github/workflows/native-builds.yml` 增加原生平台构建。它使用 ARM64 Ubuntu runner
加 Debian 12 容器、Apple Silicon 和 Intel macOS runner，以及 Windows runner。
Windows 任务使用 CPython 的 `PCbuild` 和 `PC/layout` 工具，不使用 MinGW 或 Linux
交叉编译器。`ts-build02` 上的 Docker 仅限 Linux，不属于该矩阵。

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
