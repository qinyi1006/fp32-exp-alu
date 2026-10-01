#!/usr/bin/env python3
"""Exhaustive RTL extension-range test, then 80-digit boundary rechecks.

Run from any directory. Uses only the Python standard library and Icarus.
Production RTL and the original [-64,64] reference model are left unchanged.
"""
import csv
import hashlib
import json
import math
import subprocess
import sys
from decimal import Decimal, localcontext
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BUILD = ROOT / 'build/range_boundary'
sys.path.insert(0, str(ROOT / 'scripts'))
from debug_exp import tool
from verify_model import bits, value


def run(command, logfile):
    print('Running:', ' '.join(map(str, command)), flush=True)
    with logfile.open('w') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f'Command failed; see {logfile}\n{logfile.read_text()}')


def nearest_fp32(reference):
    """Round positive Decimal to binary32, ties to even, including subnormals."""
    overflow_midpoint = Decimal(2)**128 - Decimal(2)**103
    if reference >= overflow_midpoint:
        return 0x7f800000
    try:
        candidate = bits(float(reference))
    except OverflowError:
        candidate = 0x7f7fffff
    candidates = range(max(0, candidate-2), min(0x7f7fffff, candidate+2)+1)
    return min(candidates, key=lambda u: (abs(Decimal.from_float(value(u))-reference), u & 1))


def classify(u):
    if (u & 0x7f800000) == 0x7f800000:
        return 'nan' if u & 0x7fffff else 'infinity'
    if (u & 0x7fffffff) == 0:
        return 'zero'
    return 'subnormal' if (u & 0x7f800000) == 0 else 'normal'


def check_reference_rounding():
    # Exact binary midpoints need more than 150 decimal digits for subnormals.
    with localcontext() as ctx:
        ctx.prec = 200
        cases = [(Decimal(0), 0), (Decimal(1), 0x3f800000),
                 (Decimal(2)**-149, 1), (Decimal(2)**-150, 0),
                 (3*Decimal(2)**-150, 2), (Decimal(2)**-126, 0x00800000),
                 (Decimal(2)**128-Decimal(2)**103, 0x7f800000),
                 (Decimal(1)+Decimal(2)**-24, 0x3f800000),
                 (Decimal(1)+3*Decimal(2)**-24, 0x3f800002)]
        for ref, expected in cases:
            assert nearest_fp32(ref) == expected, (ref, expected)


def describe(u, out):
    x, y = value(u), value(out)
    # For extreme FP32 inputs exp(x) need not be materialized to classify it.
    # All detailed boundary/error cases fall in [-128,128].
    with localcontext() as ctx:
        ctx.prec = 80
        reference = Decimal.from_float(x).exp() if abs(x) <= 128 else None
        golden = nearest_fp32(reference) if reference is not None else (0x7f800000 if x > 0 else 0)
        error = abs(Decimal.from_float(y)-reference)/reference if reference is not None and math.isfinite(y) else None
    return {
        'input_hex': f'0x{u:08x}', 'x': x,
        'rtl_output_hex': f'0x{out:08x}', 'rtl_class': classify(out),
        'rtl_value': y if math.isfinite(y) else classify(out),
        'golden_fp32_hex': f'0x{golden:08x}', 'golden_class': classify(golden),
        'reference_exp_decimal': str(reference) if reference is not None else None,
        'relative_error_decimal': str(error) if error is not None else None,
        'relative_error': float(error) if error is not None else None,
        'meets_relative_1e_5': error is not None and error <= Decimal('1e-5'),
        'matches_rounded_golden': out == golden,
    }


def main():
    check_reference_rounding()
    BUILD.mkdir(parents=True, exist_ok=True)
    rtl = ROOT / 'rtl/exp_fp32.v'
    rtl_bytes = rtl.read_bytes()
    sha = hashlib.sha256(rtl_bytes).hexdigest()
    binary = BUILD / 'sweep.vvp'
    run([tool('iverilog', 'IVERILOG'), '-g2012', '-Wall', '-s', 'tb_range_boundary',
         '-o', str(binary), str(rtl), str(HERE/'tb_range_boundary.sv')], BUILD/'compile.log')
    run([tool('vvp', 'VVP'), str(binary), '+summary='+str(BUILD/'sweep.json')], BUILD/'simulation.log')
    sweep = json.loads((BUILD/'sweep.json').read_text())
    assert sweep['start_bits'] == '42800000' and sweep['stop_bits'] == '43000000'
    expected_count = 0x43000000 - 0x42800000 + 1
    assert all(s['cases'] == expected_count for s in sweep['sides'])

    # Inspect neighboring *representable* inputs, not decimal approximations.
    inputs = {bits(x) for x in (0, -0.0, 1, -1, 64, -64, 65, -65, 80, -80,
                                87, -87, 88, -88, 89, -89, 90, -90,
                                100, -100, 104, -104, 127, -127, 128, -128,
                                129, -129, 256, -256)}
    inputs.update((0x7f7fffff, 0xff7fffff, 0x3d314b3f))
    centers = [bits(n*math.log(2)) for n in (126, 127, 128, 149, 150)] + [bits(128)]
    for s in sweep['sides']:
        centers.extend(int(s[k], 16) & 0x7fffffff for k in ('first_bad_input', 'worst_prefix_input'))
    for center in centers:
        for delta in range(-8, 9):
            for sign in (0, 0x80000000):
                inputs.add((center+delta) | sign)
    inputs = sorted(inputs)
    (HERE/'inputs.json').write_text(json.dumps([f'0x{u:08x}' for u in inputs], indent=2)+'\n')
    run([sys.executable, str(ROOT/'scripts/debug_exp.py'), '--inputs', str(HERE/'inputs.json'),
         '--out', str(BUILD/'debug')], BUILD/'debug.log')
    with (BUILD/'debug/signals.csv').open() as f:
        snapshots = list(csv.DictReader(f))
    assert [int(r['x'], 16) for r in snapshots] == inputs
    details = []
    for u, row in zip(inputs, snapshots):
        item = describe(u, int(row['y'], 16))
        item['signals'] = {k: row[k] for k in ('magnitude', 'y_q24', 'k', 'j', 'r_q24',
                                             'mant_q24', 'rounded_sig', 'output_exp')}
        details.append(item)
    by_input = {d['input_hex'][2:]: d for d in details}
    for side in sweep['sides']:
        good = by_input[side['last_good_input']]
        bad = by_input[side['first_bad_input']]
        assert int(side['first_bad_input'], 16) == int(side['last_good_input'], 16)+1
        assert good['rtl_output_hex'][2:] == side['last_good_output']
        assert bad['rtl_output_hex'][2:] == side['first_bad_output']
        assert good['meets_relative_1e_5'] and not bad['meets_relative_1e_5']
        side['last_good'] = good
        side['first_bad'] = bad
        side['worst_prefix'] = by_input[side['worst_prefix_input']]
        # Decimal confirms each representable neighbor's pass/fail transition.
        center = int(side['first_bad_input'], 16)
        for delta in range(-8, 9):
            assert by_input[f'{center+delta:08x}']['meets_relative_1e_5'] == (delta < 0)
    assert rtl.read_bytes() == rtl_bytes, 'RTL changed during the run'
    report = {
        'rtl_sha256': sha,
        'criterion': 'abs(RTL-exp(x))/exp(x) <= 1e-5; NaN/Inf RTL fails finite relative-error test',
        'scope': 'All FP32 inputs with 64 <= abs(x) <= 128, both signs, direct RTL simulation',
        'rtl_cases': sum(s['cases'] for s in sweep['sides']),
        'reference': 'Icarus $exp binary64 during sweep; Python Decimal 80 digits for focused cases',
        'focused_rtl_cases': len(details),
        'sweep': sweep, 'details': details,
    }
    (HERE/'results.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    fields = ['input_hex', 'x', 'rtl_output_hex', 'rtl_class', 'rtl_value',
              'golden_fp32_hex', 'golden_class', 'relative_error_decimal',
              'meets_relative_1e_5', 'matches_rounded_golden']
    with (HERE/'cases.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader(); writer.writerows(details)
    print(json.dumps({'rtl_cases': report['rtl_cases'], 'focused_cases': len(details),
                      'boundaries': [s['last_good'] for s in sweep['sides']]}, indent=2), flush=True)
    print('Report:', HERE/'results.json')
    print('All signal values:', BUILD/'debug/signals.csv')


if __name__ == '__main__':
    main()
