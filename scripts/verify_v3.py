#!/usr/bin/env python3
"""V3 negative-range regression and exhaustive RTL packing checks."""
import csv
import hashlib
import json
import math
import random
import re
import subprocess
import sys
from decimal import Decimal, localcontext
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT/'build/v3'
sys.path.insert(0, str(ROOT/'scripts'))
from verify_model import bits, value, Q, LOG2E, C1, C2, TABLE
from debug_exp import tool

LOWER = value(0xc2ce8ed0)
UPPER = value(0x42b17217)


def components(u):
    e = (u >> 23) & 255
    sig = (u & 0x7fffff) | (0x800000 if e else 0)
    mag = sig << (e-126) if e >= 126 else sig >> (126-e)
    yq = ((-mag if u >> 31 else mag)*LOG2E) // (1 << 30)
    k, fraction = divmod(yq, Q)
    j, r = divmod(fraction, 1 << 19)
    t = C1 + r*C2//Q
    h = r*t//Q
    return k, TABLE[j] + TABLE[j]*h//Q


def rne_shift(m, shift):
    quotient, remainder = divmod(m, 1 << shift)
    half = 1 << (shift-1)
    return quotient + (remainder > half or (remainder == half and quotient & 1))


def expected(u):
    x = value(u)
    if math.isnan(x): return 0x7fc00000
    if x > UPPER: return 0x7f800000
    if x < LOWER: return 0
    k, m = components(u)
    if k < -126:
        return rne_shift(m, -k-125)
    sig = rne_shift(m, 1)
    carry = sig >> 24
    return ((k+127+carry) << 23) | ((sig >> carry) & 0x7fffff)


def structural_checks(v2, v3):
    strip = lambda s: re.sub(r'//[^\n]*|/\*.*?\*/', '', s, flags=re.S)
    clean = strip(v3)
    assert not re.search(r'\b(if|always|always_comb|always_ff|signed|reg|initial|TIE_FLOP)\b|\$signed|\x27[sS]', clean)
    assert v3.count('// please add tie pipe here') == 8
    pattern = r'wire\s+(?:\[[^\]]+\]\s+)?(\w+)\s*=\s*([^;]+);'
    old, new = dict(re.findall(pattern, strip(v2))), dict(re.findall(pattern, clean))
    changed = {'saturate_low', 'negative_y_q24', 'y_q24', 'k', 'round_up',
               'rounded_sig', 'output_exp', 'core_y'}
    assert {k for k in old if new.get(k) != old[k]} == changed
    assert new['saturate_high'] == old['saturate_high']
    assert "31'h42ce8ed0" in new['saturate_low']
    new['y'] = re.search(r'assign y = ([^;]+);', clean)[1]
    active, done = set(), set()
    def visit(name):
        assert name not in active, f'Feedback through {name}'
        if name in done: return
        active.add(name)
        for dep in set(re.findall(r'\b\w+\b', new[name])) & new.keys(): visit(dep)
        active.remove(name); done.add(name)
    for name in new: visit(name)


def run(command, logfile):
    print('Running:', ' '.join(map(str, command)), flush=True)
    with logfile.open('w') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode: raise RuntimeError(logfile.read_text())


def main():
    BUILD.mkdir(parents=True, exist_ok=True)
    paths = [ROOT/'rtl/exp_fp32_v2.v', ROOT/'rtl/exp_fp32_v3.v']
    sources = [p.read_bytes() for p in paths]
    structural_checks(*(s.decode() for s in sources))
    # Reference rounding unit checks cover ties, retained even/odd LSB, and carry.
    assert [rne_shift(n, 2) for n in (4, 5, 6, 7, 10, 14)] == [1, 1, 2, 2, 2, 4]
    assert rne_shift((1 << 25)-1, 2) == 0x00800000
    base = BUILD/'base_vectors.txt'
    run([sys.executable, str(ROOT/'scripts/verify_model.py'), '--output', str(base)], BUILD/'base_model.log')
    focused = [0, 0x80000000, 0xc2ce8ed0, 0xc2ce8ecf, 0xc2ce8ed1,
               0xc2aeac4f, 0xc2aeac50, 0xc2aeac51, 0x42b17216, 0x42b17217, 0x42b17218,
               bits(-88), bits(-89), bits(-100), bits(-103), bits(-104), bits(128), bits(-128),
               0x7f800000, 0xff800000, 0x7f7fffff, 0xff7fffff, 0x7f800001, 0xff800001,
               0x7fc00000, 0xffffffff, 1, 0x80000001, 0x007fffff, 0x00800000,
               0x807fffff, 0x80800000, 0x3d314b3f]
    centers = [0x42ce8ed0, 0x42aeac50, 0x42b17217, bits(64), bits(128)]
    centers += [bits(-k*math.log(2)) for k in range(-151, -124)]
    for center in centers:
        for delta in range(-16, 17):
            for sign in (0, 0x80000000): focused.append((center+delta)|sign)
    # Probe mathematical subnormal rounding midpoints, including very small counts.
    for n in sorted(set(range(1, 65)) | {2**k+d for k in range(7, 23) for d in (-1, 0, 1)}):
        center = bits(math.log((n+0.5)*2**-149))
        focused.extend(center+d for d in range(-4, 5))
    for e in range(256):
        for f in (0, 1, 2, 0x3fffff, 0x400000, 0x7ffffe, 0x7fffff):
            for sign in (0, 0x80000000): focused.append(sign | (e << 23) | f)
    focused += [0xc2ce8ed1, bits(1), 0xc2ce8ed0, 0xc2ce8ed0, 0x7fc00001,
                bits(-100), 0x7f800000, 0x42b17217, 0xff800000, 0x80000000]
    rng = random.Random(20261008)
    random_cases = [rng.getrandbits(32) for _ in range(300000)]
    random_cases += [bits(rng.uniform(LOWER, -87.0)) for _ in range(100000)]
    vectors = BUILD/'vectors.txt'
    with vectors.open('w') as dst:
        for u in focused: dst.write(f'{u:08x} {expected(u):08x} 0\n')
        with base.open() as src:
            for line in src: dst.write(line)
        for u in random_cases: dst.write(f'{u:08x} {expected(u):08x} 0\n')
    (BUILD/'inputs.json').write_text(json.dumps([f'0x{u:08x}' for u in focused], indent=2)+'\n')
    binary = BUILD/'v3.vvp'
    run([tool('iverilog', 'IVERILOG'), '-g2012', '-Wall', '-s', 'tb_exp_fp32_v3',
         '-o', str(binary), *map(str, paths), str(ROOT/'tb/tb_exp_fp32_v3.sv')], BUILD/'compile.log')
    run([tool('vvp', 'VVP'), str(binary), '+vectors='+str(vectors),
         '+csv='+str(BUILD/'directed.csv'), '+summary='+str(BUILD/'simulation.json'),
         '+directed='+str(len(focused))], BUILD/'simulation.log')
    result = json.loads((BUILD/'simulation.json').read_text())
    base_count = json.loads(base.with_suffix('.json').read_text())['vectors']
    assert result['vector_cases'] == base_count+len(focused)+len(random_cases)
    assert result['dense_cases'] == 16777218
    assert result['total_cases'] == result['dense_cases']+result['vector_cases']
    assert sum(result[k] for k in ('normal_cases','subnormal_cases','high_cases','low_cases','nan_cases')) == result['total_cases']
    assert all(p.read_bytes()==s for p,s in zip(paths,sources))
    with (BUILD/'directed.csv').open() as f: rows = list(csv.DictReader(f))
    assert len(rows) == len(focused)
    sys.path.insert(0, str(ROOT/'analysis/range_boundary'))
    from run import describe, check_reference_rounding
    check_reference_rounding()
    selected = [0xc2ce8ed0, 0xc2ce8ecf, 0xc2ce8ed1, 0xc2aeac50,
                bits(-88), bits(-89), bits(-100), bits(-103), 0x42b17217]
    outputs = {int(r['input_hex'],16): int(r['output_hex'],16) for r in rows}
    for metric in ('normal', 'subnormal', 'subnormal_ulp', 'algorithm'):
        u = int(result[f'worst_{metric}_input'],16)
        out = int(result[f'worst_{metric}_output'],16)
        assert out == expected(u)
        outputs[u] = out; selected.append(u)
    details = [describe(u,outputs[u]) for u in dict.fromkeys(selected)]
    for d in details:
        u=int(d['input_hex'],16)
        if LOWER <= value(u) <= UPPER:
            k,m=components(u)
            with localcontext() as ctx:
                ctx.prec=80
                ref=Decimal.from_float(value(u)).exp()
                approximation=Decimal(m)/Q * Decimal(2)**k
                alg_error=abs(approximation-ref)/ref
                assert alg_error < Decimal('1e-5')
                d['unrounded_relative_error_decimal']=str(alg_error)
                if ref < Decimal(2)**-126:
                    abs_error=abs(Decimal.from_float(value(outputs[u]))-ref)
                    assert abs_error <= ref*Decimal('1e-5') + Decimal(2)**-150
                else: assert d['meets_relative_1e_5']
        d['ulp_distance_to_math_golden'] = abs(outputs[u]-int(d['golden_fp32_hex'],16))
    result.update(validation_date='2026-10-08', baseline_cases=base_count,
                  focused_cases=len(focused), random_cases=len(random_cases), seed=20261008,
                  v2_rtl_sha256=hashlib.sha256(sources[0]).hexdigest(),
                  v3_rtl_sha256=hashlib.sha256(sources[1]).hexdigest(),
                  lower_hex='c2ce8ed0', upper_hex='42b17217', details=details,
                  scope='All FP32 magnitudes [64,128], both signs; regression, directed and random elsewhere',
                  subnormal_criterion='RNE of the Q24 approximation; abs(error) <= exp(x)*1e-5 + 2^-150; not correctly rounded mathematical exp')
    (BUILD/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='details'},indent=2),flush=True)


if __name__ == '__main__': main()
