# FP32 exp(x) 前向组合计算单元

输入、输出均为 FP32。对有限输入 `x ∈ [-64,64]`，目标最大相对误差 `1e-5`。
采用 32 项常数表与二次多项式；内部只用整数乘加、移位和选择。

- `docs/design.md`：算法、位宽、全区间误差预算、资源构成与七级流水线建议。
- `rtl/exp_fp32.v`：组合 Verilog，无 if、always、时钟或反馈。
- `tb/tb_exp_fp32.sv`：逐位模型对比及数学参考误差检查。
- `scripts/verify_model.py`：定点模型、测试向量生成和误差预算复算。
- `scripts/generate_lut.py`：重生成 RTL 内的均衡查表选择树。
- `docs/tools.md`：工具版本、位置、来源及安装原因。
- `docs/validation.md`：实际验证结果及未验证事项。
- [Q 格式误差研究](analysis/q_sweep/README.md)：Q12～Q26 最大相对误差曲线、全区间模型搜索、原始数据和复现脚本。
- [TIE 对照调试](docs/debug.md)：自定义 32 位输入数组，导出全部信号的稳定值和逐次更新 CSV。

在本目录执行：

```sh
bash run.sh
```

脚本优先使用项目内的 Icarus Verilog，否则使用 PATH 中的 `iverilog`/`vvp`。
也可通过 `IVERILOG`、`VVP`、`PYTHON` 环境变量指定工具路径。
默认生成约 45 万个去重输入；快速检查可运行 `bash run.sh --random 1000`。
`--random N` 为每种随机分布的抽样次数，定向边界测试始终保留。
编译、模型和仿真结果写入 `build/`。任意编译错误、位不一致或误差超限会使脚本失败。
无需 Python 第三方依赖。

调试指定输入时，编辑 `debug/inputs.json`，执行 `bash debug.sh`。
结果位于 `build/debug/signals.csv`（每例全部信号稳定值）和 `build/debug/signal_updates.csv`（逐次信号更新）。

实际打拍由 TIE 转译完成，位置以 `// please add tie pipe here` 标记。
插入寄存器时必须按注释对齐所有旁路信号。七拍划分未经目标时钟的静态时序验证。
区间外输入及 NaN/Inf 的行为尚未约定，本实现不保证其结果。
