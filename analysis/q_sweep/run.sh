#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p build
CC="${CC:-clang}"
BASE_PYTHON="${BASE_PYTHON:-python3}"
BUNDLED_PYTHON=/Users/yi.qin/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3
if [[ -z "${PLOT_PYTHON:-}" ]]; then
  if [[ -x "$BUNDLED_PYTHON" ]]; then PLOT_PYTHON="$BUNDLED_PYTHON"; else PLOT_PYTHON=python3; fi
fi
if [[ ! -f build/vectors.txt || ! -f build/exp_fp32.vvp ]]; then bash run.sh; fi
"$CC" -O3 -std=c11 -Wall -Wextra analysis/q_sweep/sweep.c -lm -o build/q_sweep
case "$(uname -s)" in
  Darwin) SHARED_FLAGS=(-dynamiclib) ;;
  *) SHARED_FLAGS=(-shared -fPIC) ;;
esac
"$CC" -O3 -std=c11 -DMODEL_LIBRARY "${SHARED_FLAGS[@]}" analysis/q_sweep/sweep.c -lm -o build/q_model.dylib
"$BASE_PYTHON" analysis/q_sweep/verify_models.py | tee build/q-model-check.log
build/q_sweep 12 26 > analysis/q_sweep/results.csv 2> build/q-sweep-progress.log
export PYTHONPATH="$PWD/.tools/q-sweep-python${PYTHONPATH:+:$PYTHONPATH}"
"$PLOT_PYTHON" analysis/q_sweep/plot_results.py | tee build/q-plot.log
"$BASE_PYTHON" - <<'PY'
import json, math, sys
from pathlib import Path
sys.path.insert(0,'scripts')
from verify_model import model, value
rows=json.loads(Path('analysis/q_sweep/results.json').read_text())['data']
r=next(r for r in rows if r['series']=='datapath' and r['input_fraction_bits']==24)
u=int(r['worst_input_hex'],16); out=int(r['worst_output_hex'],16)
assert model(u)==out
Path('build/q24_exhaustive_worst.txt').write_text(f'{u:08x} {out:08x} {math.exp(value(u)):.17e}\n')
PY
if [[ -x .tools/iverilog-12.0/bin/vvp ]]; then DEFAULT_VVP="$PWD/.tools/iverilog-12.0/bin/vvp"; else DEFAULT_VVP=vvp; fi
"${VVP:-$DEFAULT_VVP}" build/exp_fp32.vvp +vectors=build/q24_exhaustive_worst.txt | tee build/q24-worst-rtl.log
