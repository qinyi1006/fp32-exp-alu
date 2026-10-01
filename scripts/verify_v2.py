#!/usr/bin/env python3
"""Reproducible v2 regression; standard library + Icarus, no RTL mutation."""
import csv
import hashlib
import json
import math
import random
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'build/v2'
sys.path.insert(0, str(ROOT/'scripts'))
from verify_model import model, value, bits
from debug_exp import tool

LOWER = -87.3365478515625
UPPER = 88.72283172607421875


def expected(u):
    x = value(u)
    if math.isnan(x):
        return 0x7fc00000
    if x > UPPER:
        return 0x7f800000
    if x < LOWER:
        return 0
    return model(u)


def run(command, log_path):
    print('Running:', ' '.join(map(str, command)), flush=True)
    with log_path.open('w') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(log_path.read_text())


def check_structure(original, v2):
    def strip(s):
        return re.sub(r'//[^\n]*|/\*.*?\*/', '', s, flags=re.S)
    clean = strip(v2)
    assert not re.search(r'\b(if|always|always_comb|always_ff|signed|reg|initial|TIE_FLOP)\b|\$signed|\x27[sS]', clean)
    assert v2.count('// please add tie pipe here') == 7
    # All original combinational wire expressions are literally preserved.
    declaration = r'wire\s+(?:\[[^\]]+\]\s+)?(\w+)\s*=\s*([^;]+);'
    old = dict(re.findall(declaration, strip(original)))
    new = dict(re.findall(declaration, clean))
    assert all(new.get(k) == expr for k, expr in old.items())
    old_output = re.search(r'assign y = ([^;]+);', original)[1]
    assert new['core_y'] == old_output
    assert set(new)-set(old) == {'input_nan', 'saturate_high', 'saturate_low', 'core_y'}
    # Detect feedback among continuous wire assignments and the output.
    new['y'] = re.search(r'assign y = ([^;]+);', clean)[1]
    active, done = set(), set()
    def visit(name):
        assert name not in active, f'Feedback through {name}'
        if name in done:
            return
        active.add(name)
        for dep in set(re.findall(r'\b\w+\b', new[name])) & new.keys():
            visit(dep)
        active.remove(name); done.add(name)
    for name in new:
        visit(name)


def main():
    BUILD.mkdir(parents=True, exist_ok=True)
    original_path, v2_path = ROOT/'rtl/exp_fp32.v', ROOT/'rtl/exp_fp32_v2.v'
    original_bytes, v2_bytes = original_path.read_bytes(), v2_path.read_bytes()
    check_structure(original_bytes.decode(), v2_bytes.decode())
    # Regenerate the original 454,400 reference vectors in a separate directory.
    base = BUILD/'base_vectors.txt'
    run([sys.executable, str(ROOT/'scripts/verify_model.py'), '--output', str(base)], BUILD/'base_model.log')
    focused = [0, 0x80000000, bits(LOWER), bits(UPPER), bits(LOWER)+1, bits(UPPER)+1,
               bits(LOWER)-1, bits(UPPER)-1, bits(-88), bits(90), bits(-128), bits(128),
               0x7f800000, 0xff800000, 0x7f7fffff, 0xff7fffff,
               0x7f800001, 0xff800001, 0x7fc00000, 0xffffffff, 1, 0x80000001,
               0x007fffff, 0x00800000, 0x807fffff, 0x80800000, 0x3d314b3f]
    # Strict threshold tests on both signs, including equal boundaries.
    for center in (bits(LOWER)&0x7fffffff, bits(UPPER), bits(64), bits(128)):
        for delta in range(-32, 33):
            for sign in (0, 0x80000000):
                focused.append((center+delta)|sign)
    # Every exponent, both signs, representative mantissa ends and midpoints.
    for exponent in range(256):
        for fraction in (0, 1, 2, 0x3fffff, 0x400000, 0x7ffffe, 0x7fffff):
            for sign in (0, 0x80000000):
                focused.append(sign | (exponent<<23) | fraction)
    # Deliberate back-to-back category changes and identical repeated inputs.
    focused.extend([bits(UPPER)+1, bits(0), bits(LOWER)+1, bits(1), 0x7fc00001,
                    bits(-1), 0x7f800000, bits(UPPER), 0xff800000, bits(LOWER),
                    bits(LOWER), bits(UPPER), bits(UPPER)])
    rng = random.Random(20261001)
    random_cases = [rng.getrandbits(32) for _ in range(300000)]
    vectors = BUILD/'vectors.txt'
    with vectors.open('w') as dst:
        for u in focused:
            dst.write(f'{u:08x} {expected(u):08x} 0\n')
        with base.open() as src:
            for line in src:
                dst.write(line)
        for u in random_cases:
            dst.write(f'{u:08x} {expected(u):08x} 0\n')
    (BUILD/'inputs.json').write_text(json.dumps([f'0x{u:08x}' for u in focused], indent=2)+'\n')
    binary = BUILD/'v2.vvp'
    run([tool('iverilog', 'IVERILOG'), '-g2012', '-Wall', '-s', 'tb_exp_fp32_v2',
         '-o', str(binary), str(original_path), str(v2_path), str(ROOT/'tb/tb_exp_fp32_v2.sv')], BUILD/'compile.log')
    run([tool('vvp', 'VVP'), str(binary), '+vectors='+str(vectors),
         '+csv='+str(BUILD/'directed.csv'), '+summary='+str(BUILD/'simulation.json'),
         '+directed='+str(len(focused))], BUILD/'simulation.log')
    result = json.loads((BUILD/'simulation.json').read_text())
    base_count = json.loads(base.with_suffix('.json').read_text())['vectors']
    assert result['vector_cases'] == len(focused)+base_count+len(random_cases)
    assert result['dense_cases'] == 16777218
    assert result['total_cases'] == result['dense_cases']+result['vector_cases']
    assert sum(result[k] for k in ('in_range','saturated_high','flushed_low','nan_cases')) == result['total_cases']
    assert all(result[k]>0 for k in ('in_range','saturated_high','flushed_low','nan_cases'))
    # High precision recheck of threshold and worst-case values using RTL output.
    sys.path.insert(0, str(ROOT/'analysis/range_boundary'))
    from run import describe
    with (BUILD/'directed.csv').open() as f:
        rows = list(csv.DictReader(f))
    by_input = {int(r['input_hex'],16): int(r['output_hex'],16) for r in rows}
    assert len(rows) == len(focused)
    worst = int(result['worst_input_hex'],16)
    high_precision = [describe(u,by_input[u]) for u in dict.fromkeys([bits(LOWER), bits(UPPER), 0x3d314b3f, worst])]
    assert all(d['meets_relative_1e_5'] for d in high_precision)
    assert original_path.read_bytes() == original_bytes and v2_path.read_bytes() == v2_bytes
    result.update(original_rtl_sha256=hashlib.sha256(original_bytes).hexdigest(),
                  v2_rtl_sha256=hashlib.sha256(v2_bytes).hexdigest(),
                  baseline_cases=base_count, focused_cases=len(focused), random_cases=len(random_cases),
                  seed=20261001, high_precision_rechecks=high_precision,
                  structure_checks='All old wire expressions unchanged; no feedback/prohibited RTL syntax; 7 pipeline markers',
                  scope='Exhaustive 64<=abs(x)<=128; original regression plus directed/full-bit random elsewhere; not all 2^32 inputs')
    (BUILD/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2), flush=True)


if __name__ == '__main__':
    main()
