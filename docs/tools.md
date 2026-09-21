# 验证工具与安装记录

所有本次新增工具均安装在 `/Users/yi.qin/Desktop/exp/.tools/` 下，没有修改系统安装目录。
`run.sh` 运行只需要 Python 3、Icarus Verilog 的 `iverilog` 与 `vvp`。

| 工具 | 版本 | 安装位置 | 安装原因 |
|---|---|---|---|
| Icarus Verilog（含 vvp） | 12.0 | `/Users/yi.qin/Desktop/exp/.tools/iverilog-12.0` | 本机无 Verilog 仿真器，用于编译 RTL/testbench 和运行误差测试 |
| GNU Bison | 3.8.2 | `/Users/yi.qin/Desktop/exp/.tools/bison-3.8.2-install` | 系统 Bison 2.3 无法编译 Icarus 的 VHDL 解析器，属于构建依赖，运行测试不再需要 |

使用的原有工具（本次未安装）：

- `/usr/bin/python3`：Python 3.9.6，标准库用于向量生成、浮点参考和误差分析。
- `/usr/bin/clang` / CommandLineTools：Apple clang 21.0.0，用于编译仿真器与 Bison。
- `/usr/bin/make`：GNU Make 3.81。
- `/usr/bin/flex`：flex 2.6.4 Apple(flex-35)。
- `/usr/bin/m4`：GNU M4 1.4.6，Bison 构建/运行所需的已有工具。
- `/usr/bin/curl`、`tar`、`shasum`：下载、解包和校验源码。

## 来源与源码校验

Icarus 官方仓库：<https://github.com/steveicarus/iverilog>。
采用其 12.0 发布版源码包：
<https://downloads.sourceforge.net/project/iverilog/iverilog/12.0/verilog-12.0.tar.gz>。

SHA-256：

```text
03848551a9c5ec390fefcff1bbcca14765c7aa035ee85bc9cbcb0424e0149fd4
```

Bison 官方源码包：<https://ftp.gnu.org/gnu/bison/bison-3.8.2.tar.xz>。

SHA-256：

```text
9bba0214ccf7f1079c5d59210045227bcf619519840ebfa80cd3849cff5a5bf2
```

源码分别保存在 `.tools/verilog-12.0/` 与 `.tools/bison-3.8.2/`，许可证在各源码目录内。
下载归档位于 `/tmp/exp-verilog-12.0.tar.gz` 和 `/tmp/exp-bison-3.8.2.tar.xz`，临时目录可能由系统清理。
构建日志位于 `build/iverilog-configure.log`、`build/iverilog-build.log`、`build/iverilog-install.log`、`build/bison-configure.log`、`build/bison-build.log`、`build/bison-install.log`。

## 复现构建

在源码包解压到项目 `.tools/` 后执行以下命令；可将 EXP_ROOT 换成新的项目绝对路径。

```sh
EXP_ROOT=/Users/yi.qin/Desktop/exp
cd "$EXP_ROOT/.tools/bison-3.8.2"
./configure --prefix="$EXP_ROOT/.tools/bison-3.8.2-install"
make -j4
make install
cd "$EXP_ROOT/.tools/verilog-12.0"
./configure --prefix="$EXP_ROOT/.tools/iverilog-12.0"
make -j4 YACC="$EXP_ROOT/.tools/bison-3.8.2-install/bin/bison"
make install YACC="$EXP_ROOT/.tools/bison-3.8.2-install/bin/bison"
cd "$EXP_ROOT"
bash run.sh
```

也可使用已安装的 Icarus 12.0；不必为了运行工程重新构建工具。

## 2026-09-17：Q 格式误差曲线分析新增工具

绘图使用 Codex 已有 Python 3.12 运行时：
`/Users/yi.qin/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3`。
该运行时未新安装。C 数值搜索继续使用已有 Apple clang 21.0.0。

本次从 PyPI 安装 Matplotlib 及其依赖至
`/Users/yi.qin/Desktop/exp/.tools/q-sweep-python/`，用于绘制科学误差曲线并导出 PNG、SVG；未修改系统 Python。
实际安装版本：Matplotlib 3.11.2、NumPy 2.5.3、ContourPy 1.4.0、cycler 0.12.1、fonttools 4.65.0、kiwisolver 1.5.1、packaging 26.3、Pillow 12.3.0、pyparsing 3.3.2、python-dateutil 2.9.0.post0、six 1.17.0。
除 Matplotlib 外均为其绘图、数值或图像输出依赖。安装日志：`build/q-sweep-pip.log`。
Matplotlib 字体缓存位于 `.tools/mplconfig/`；图中的中文使用 macOS 已有 Hiragino Sans GB 字体。
