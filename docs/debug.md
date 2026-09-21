# TIE 对照调试：自定义输入与全部信号 CSV

编辑 [debug/inputs.json](../debug/inputs.json)，填入一个 32 位输入位编码数组。例如：

```json
[
  "0x3f800000",
  "0xbf800000",
  "0x42800000",
  "0xc2800000",
  "0x3d314b3f"
]
```

这些值分别表示 FP32 的 1、-1、64、-64 和当前 Q24 最坏误差输入。
数组元素是 **FP32 原始位编码**，不是十进制浮点数。支持 `"0x3f800000"`、`"3f800000"`、`"32'h3f80_0000"`，也支持 JSON 整数 `1065353216`。
不接受浮点数、布尔值、负整数、超过 32 位的整数或未知位 x/z。数组长度自动识别，顺序和重复项完整保留。

从项目目录执行：

```sh
bash debug.sh
```

自定义数组位置和输出目录：

```sh
bash debug.sh --inputs debug/my_inputs.json --out build/my_debug
```

路径按命令运行时的工作目录解释，支持路径中的空格。依赖 Python 3 标准库及已安装的 Icarus Verilog；可通过 `PYTHON`、`IVERILOG`、`VVP` 指定工具。没有新增工具安装。

## 主要输出

默认写入 `build/debug/`：

| 文件 | 内容 |
|---|---|
| `signals.csv` | 每个输入一行，等待组合逻辑稳定后记录全部信号，包括 32 项常量表和每层选择树 |
| `signal_updates.csv` | 逐条记录本次输入传播期间，事件监视器观察到的信号更新，保留仿真器输出顺序 |
| `signals_manifest.json` | 每个信号的位宽、十六进制位数和建议流水线级编号；同时记录 RTL SHA-256 |
| `summary.json` | 参考检查是否有效、逐位是否匹配、相对误差，以及用例/信号/事件计数 |
| `inputs.json` / `inputs.hex` | 本次实际运行的输入数组快照 |
| `exp_fp32.v` | 本次使用的生产 RTL 原样备份 |
| `tb_exp_fp32_debug_full.sv` | 已展开全部打印语句的独立调试 testbench，可直接检查或再次编译 |
| `debug_snapshot.svh` / `debug_monitors.svh` | 自动生成的稳定快照打印和逐信号事件监视代码 |
| `compile.log` / `simulation.log` | 编译与仿真日志；仿真控制台也逐例打印 x、y |

每次执行会覆盖所选输出目录中同名生成文件，需要保留历史时请换一个 `--out` 目录。

## signals.csv：逐级对照的主要文件

列顺序为：

```text
case_id,time_ns,x,y,input_exp,input_sig,...,output_exp,model_expected,golden_exp_fp32,reference_valid,model_match
```

所有信号数据及用例编号、时间均采用带 `0x` 前缀的十六进制，按信号宽度补足位数。
例如 32 位信号用 8 个十六进制数字，62 位乘积用 16 个；负值使用原始补码编码。
若仿真器产生未知/高阻位，会原样保留 x/z，便于定位问题。

- `case_id` 从 `0x00000000` 开始，唯一标识数组位置；即使 x 相同也能区分不同用例。
- `x`、`y` 是 DUT 输入/输出位编码；其余 RTL 信号使用源文件中的原名。
- `model_expected` 是 Python 定点算法的逐位期望输出。翻译正确的 TIE 实现应与这一列逐位一致。
- `golden_exp_fp32` 是 `math.exp(x)` 四舍六入五成双转换为 FP32 后的参考位编码。它是双精度数学库产生的参考，不宣称是形式化证明的正确舍入 exp。
- `y` 与 `golden_exp_fp32` 允许有差异，因为本设计是满足相对误差要求的近似实现。
- `reference_valid=0x1` 表示输入为 [-64,64] 内的有限数；这时 `model_match` 指示是否与当前定点模型一致。
- 区间外、NaN、Inf 照常送入 RTL 并导出全部信号，但 `reference_valid=0x0`，两个期望值写作 `0xxxxxxxxx`，`model_match=0xx`。这些输入的算法行为尚未约定。

仿真完成所有用例后才进行逐位参考检查。存在有效输入的 RTL/model 不一致时，脚本返回非零，但仍保留全部 CSV，方便分析。

## signal_updates.csv：组合传播过程

```text
update_seq,case_id,input_x,time_ns,signal,value
```

每条记录包含全局递增的十六进制序号、用例编号、本次输入、仿真时间、变化的信号名和新值。每个信号都有独立 `always @(dut.signal)` 监视器，打印位于独立 testbench 内。
同一时刻可能多次更新同一信号，按 `update_seq` 阅读；这反映零延迟组合仿真的事件调度和传播中间状态，不是实际 TIE 的时钟周期或门级物理延迟。
每个用例留 1ns 让逻辑稳定，`signals.csv` 在稳定后采样。事件记录的 `time_ns` 通常比相应用例稳定快照小 1。恒定表项初始化在施加第一个用例前完成，不会在事件 CSV 中反复出现，但每个稳定快照都包含它们。
连续两个相同输入不会产生 DUT 更新事件，仍各自输出一行稳定快照。

## 推荐的定位顺序

先用 `signals.csv` 对照同一个 `case_id`，找到最早出现不同值的一级：

1. `input_exp`、`input_sig`、`magnitude`、`negative`：检查 FP32 解码、移位位宽及符号。
2. `log_product`：检查常数 `1549082005` 以及 31×31 完整 62 位乘积是否保留。
3. `log_integer`、`log_fraction_zero`、`negative_y_q24`、`y_q24`：检查取位和负数向负无穷取整的余数修正。
4. `k`、`j`、`r_q24`、`table_q24`：检查位段划分与查表索引。
5. `c2_product`、`c2_term`、`t_q24`、`h_product`、`h_q24`：检查每次乘法后取位是否准确。
6. `correction_product`、`correction_q24`、`mant_q24`：检查校正乘积和尾数加法。
7. `round_up`、`rounded_sig`、`carry`、`fraction`、`output_exp`、`y`：检查最终舍入和 FP32 打包。

`left_amount` / `right_amount` 中未选中的分支、正输入下的 `negative_y_q24` 等也会打印；这些信号可能呈现很大的补码/无符号值，不表示实际选中的计算路径出错。
如果 TIE 已插入流水线，需要对齐各级所属输入；不能用同一时钟下来自不同输入的信号与同一 CSV 行比较。级编号见 `signals_manifest.json` 和设计文档。

## 源码组织与复现

生产文件 `rtl/exp_fp32.v` 未修改，仍遵守无 if、无 always、无 signed 的限制。打印版本由 `tb/tb_exp_fp32_debug.sv` 与 `scripts/debug_exp.py` 生成，不需要复制改写计算逻辑。
脚本识别当前 RTL 的单信号 wire 声明，自动生成全部打印列；不支持的声明形式会报错，避免遗漏。若后续增加复杂声明，应同步扩展信号枚举器。

默认输出目录中的备份可单独再次运行：

```sh
.tools/iverilog-12.0/bin/iverilog -g2012 -Wall -s tb_exp_fp32_debug \
  -o build/debug/debug.vvp build/debug/exp_fp32.v build/debug/tb_exp_fp32_debug_full.sv
.tools/iverilog-12.0/bin/vvp build/debug/debug.vvp \
  +inputs=build/debug/inputs.hex \
  +snapshots=build/debug/snapshots_raw.csv \
  +events=build/debug/events_raw.csv
```

上述直接调用产生原始无表头 CSV；运行 `bash debug.sh` 会自动完成整理，得到带表头、参考值和 `0x` 前缀的正式 CSV。

## 本次验证

默认 11 个示例全部与定点模型逐位一致，导出 **93 个信号、903 条更新记录**（Icarus Verilog 12.0）。
接口测试另覆盖十六进制格式、重复输入、±0、±64、NaN/Inf、路径空格、非法输入拒绝、打印字段宽度、RTL 原样备份，以及将事件 CSV 按序重放后与稳定快照核对。

```sh
python3 -m unittest discover -s tests -p test_debug_exp.py -v
```
