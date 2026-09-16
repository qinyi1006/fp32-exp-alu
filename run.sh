#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$PWD"
PYTHON="${PYTHON:-python3}"
if [[ -x "$ROOT/.tools/iverilog-12.0/bin/iverilog" ]]; then
  DEFAULT_IVERILOG="$ROOT/.tools/iverilog-12.0/bin/iverilog"
  DEFAULT_VVP="$ROOT/.tools/iverilog-12.0/bin/vvp"
else
  DEFAULT_IVERILOG=iverilog
  DEFAULT_VVP=vvp
fi
IVERILOG="${IVERILOG:-$DEFAULT_IVERILOG}"
VVP="${VVP:-$DEFAULT_VVP}"
command -v "$IVERILOG" >/dev/null || { echo 'Missing iverilog; see docs/tools.md' >&2; exit 1; }
command -v "$VVP" >/dev/null || { echo 'Missing vvp; see docs/tools.md' >&2; exit 1; }
mkdir -p build
"$PYTHON" scripts/verify_model.py --output build/vectors.txt "$@" | tee build/model.log
"$IVERILOG" -g2012 -Wall -s tb_exp_fp32 -o build/exp_fp32.vvp rtl/exp_fp32.v tb/tb_exp_fp32.sv 2>&1 | tee build/compile.log
"$VVP" build/exp_fp32.vvp +vectors=build/vectors.txt | tee build/simulation.log
