#!/usr/bin/env python3
"""Run a user-defined array of FP32 bit patterns and dump every RTL wire to CSV.

No third-party packages. Print code lives in a generated simulation-only testbench.
"""
import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from verify_model import model, value, bits


def read_inputs(path):
    data = json.loads(path.read_text())
    if not isinstance(data, list) or not data:
        raise ValueError('Input file must be a nonempty JSON array')
    values = []
    for i, item in enumerate(data):
        if isinstance(item, bool):
            raise ValueError(f'Input {i}: Boolean is not a 32-bit integer')
        if isinstance(item, int):
            u = item
        elif isinstance(item, str):
            s = item.strip().lower().replace('_', '')
            s = re.sub(r"^(?:0x|32'h)", '', s)
            if not re.fullmatch(r'[0-9a-f]{1,8}', s):
                raise ValueError(f'Input {i}: expected 1-8 hex digits, got {item!r}')
            u = int(s, 16)
        else:
            raise ValueError(f'Input {i}: use an integer or a hex string')
        if not 0 <= u <= 0xffffffff:
            raise ValueError(f'Input {i}: outside the uint32 range')
        values.append(u)
    return values


def discover_signals(source):
    # This intentionally recognizes only this project's scalar/constant-width
    # wire declarations. Fail closed if a future RTL change introduces a form
    # we cannot enumerate, rather than silently omitting a signal.
    stripped = re.sub(r'//[^\n]*|/\*.*?\*/', lambda m: ' ' * len(m[0]), source, flags=re.S)
    stripped = re.sub(r'^\s*`[^\n]*', lambda m: ' ' * len(m[0]), stripped, flags=re.M)
    decl = re.compile(r'\bwire\s+(?:\[\s*(\d+)\s*:\s*(\d+)\s*\]\s*)?(\w+)\s*(?=[=,;)])')
    matches = list(decl.finditer(stripped))
    if len(matches) != len(re.findall(r'\bwire\b', stripped)):
        raise ValueError('Unsupported wire declaration; extend discover_signals before dumping')
    if re.search(r'\b(?:reg|logic|integer|genvar)\b', stripped):
        raise ValueError('DUT contains non-wire signals that this enumerator does not support')
    stages = [(m.start(), int(m[1])) for m in re.finditer(r'// Stage ([1-7]):', source)]
    result = []
    for m in matches:
        tail = stripped[m.end():]
        if tail.startswith(','):
            if not re.match(r',\s*(?:input|output)\s+wire\b', tail):
                raise ValueError('Use one signal per wire declaration for debug enumeration')
        elif tail.startswith('='):
            depth = 0
            for char in tail:
                if char in '({[':
                    depth += 1
                elif char in ')}]':
                    depth -= 1
                elif char == ',' and depth == 0:
                    raise ValueError('Use one signal per wire declaration for debug enumeration')
                elif char == ';' and depth == 0:
                    break
        name = m[3]
        width = abs(int(m[1]) - int(m[2])) + 1 if m[1] else 1
        if width > 64:
            raise ValueError(f'Signal {name}: width {width} exceeds debug format limit')
        stage = next((s for pos, s in reversed(stages) if pos < m.start()), 0)
        result.append({'name': name, 'width': width, 'stage': stage,
                       'hex_digits': (width+3)//4})
    names = [s['name'] for s in result]
    if len(names) != len(set(names)) or not {'x','y'} <= set(names):
        raise ValueError('Unexpected DUT signal declarations')
    return result


def build_print_code(signals):
    formats = ['%08h', '%016h'] + [f"%0{s['hex_digits']}h" for s in signals]
    args = ['case_id', '$time'] + ['dut.'+s['name'] for s in signals]
    snap = '$fwrite(snapshot_fd, "' + ','.join(formats) + '\\n",\n    ' + ',\n    '.join(args) + ');\n'
    monitors = []
    for s in signals:
        name=s['name']
        monitors.append(f'''always @(dut.{name}) begin
    if (capture) begin
        update_seq = update_seq + 64'd1;
        $fwrite(event_fd, "%016h,%08h,%08h,%016h,{name},%0{s['hex_digits']}h\\n",
                update_seq, case_id, x, $time, dut.{name});
    end
end
''')
    return snap, '\n'.join(monitors)


def hex_value(raw, width):
    raw=raw.strip().lower()
    digits=(width+3)//4
    if not re.fullmatch(r'[0-9a-fxz]+',raw) or len(raw)>digits:
        raise ValueError(f'Malformed {width}-bit simulator value: {raw!r}')
    # Verilog may print a short all-X/all-Z value; extend those with the same symbol.
    fill = raw[0] if set(raw) <= {'x'} or set(raw) <= {'z'} else '0'
    return '0x' + raw.rjust(digits, fill)


def tool(name, override):
    candidate=os.environ.get(override)
    if candidate:
        resolved=shutil.which(candidate)
    else:
        local=ROOT/'.tools/iverilog-12.0/bin'/name
        resolved=str(local) if local.is_file() else shutil.which(name)
    if not resolved:
        raise ValueError(f'Missing {name}; set {override} or see docs/tools.md')
    return str(Path(resolved).resolve())


def run_logged(command, path):
    result=subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    path.write_text(result.stdout)
    if result.stdout:
        print(result.stdout, end='')
    if result.returncode:
        raise RuntimeError(f'Command failed ({result.returncode}); see {path}')


def convert_outputs(outdir, signals, cases, rtl_sha):
    widths={s['name']:s['width'] for s in signals}
    header=['case_id','time_ns']+[s['name'] for s in signals]
    extras=['model_expected','golden_exp_fp32','reference_valid','model_match']
    stats=[]
    with (outdir/'snapshots_raw.csv').open() as src, (outdir/'signals.csv').open('w',newline='') as dst:
        writer=csv.DictWriter(dst,fieldnames=header+extras)
        writer.writeheader()
        for i,row in enumerate(csv.reader(src)):
            if len(row)!=len(header) or i>=len(cases):
                raise ValueError('Unexpected simulator snapshot dimensions')
            r=dict(zip(header,row))
            if int(r['case_id'],16)!=i or int(r['x'],16)!=cases[i]:
                raise ValueError(f'Simulator input order mismatch at case {i}')
            norm={k:hex_value(v,widths.get(k,32 if k=='case_id' else 64)) for k,v in r.items()}
            u=cases[i]; x=value(u)
            valid=math.isfinite(x) and abs(x)<=64
            expected=model(u) if valid else None
            golden=bits(math.exp(x)) if valid else None
            actual=None if re.search('[xz]',r['y']) else int(r['y'],16)
            match=valid and actual==expected
            rel=abs(value(actual)-math.exp(x))/math.exp(x) if valid and actual is not None else None
            norm.update(model_expected=f'0x{expected:08x}' if valid else '0xxxxxxxxx',
                        golden_exp_fp32=f'0x{golden:08x}' if valid else '0xxxxxxxxx',
                        reference_valid='0x1' if valid else '0x0',
                        model_match=('0x1' if match else '0x0') if valid else '0xx')
            writer.writerow(norm)
            stats.append({'case_id':i,'x_hex':f'{u:08x}','reference_valid':valid,
                          'model_match':match if valid else None,'relative_error':rel})
    if len(stats)!=len(cases):
        raise ValueError('Simulator did not dump every input case')
    # Keep the exact event order emitted by the simulator. No sorting/coalescing.
    n_events=0
    with (outdir/'events_raw.csv').open() as src, (outdir/'signal_updates.csv').open('w',newline='') as dst:
        writer=csv.writer(dst)
        writer.writerow(['update_seq','case_id','input_x','time_ns','signal','value'])
        for row in csv.reader(src):
            if len(row)!=6 or row[4] not in widths:
                raise ValueError('Malformed signal-update record')
            seq,cid,x,time,name,v=row
            case_num=int(cid,16)
            if not 0<=case_num<len(cases) or int(x,16)!=cases[case_num] or int(seq,16)!=n_events+1:
                raise ValueError('Inconsistent signal-update ordering/input metadata')
            writer.writerow([hex_value(seq,64),hex_value(cid,32),hex_value(x,32),hex_value(time,64),name,hex_value(v,widths[name])])
            n_events+=1
    summary={'cases':len(cases),'signals':len(signals),'signal_updates':n_events,
             'valid_reference_cases':sum(r['reference_valid'] for r in stats),
             'model_mismatches':sum(r['model_match'] is False for r in stats),
             'rtl_sha256':rtl_sha,'details':stats}
    (outdir/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs',type=Path,default=ROOT/'debug/inputs.json',help='JSON array of uint32 or hex strings')
    p.add_argument('--out',type=Path,default=ROOT/'build/debug',help='Directory for CSV and simulator debug code')
    args=p.parse_args()
    cases=read_inputs(args.inputs.resolve())
    rtl=ROOT/'rtl/exp_fp32.v'
    out=args.out.resolve()
    if (out/'exp_fp32.v').resolve()==rtl.resolve():
        raise ValueError('--out cannot point to the production RTL directory')
    out.mkdir(parents=True,exist_ok=True)
    source=rtl.read_text(); sha=hashlib.sha256(rtl.read_bytes()).hexdigest()
    signals=discover_signals(source)
    (out/'signals_manifest.json').write_text(json.dumps({'rtl_sha256':sha,'signals':signals},indent=2)+'\n')
    (out/'inputs.hex').write_text(''.join(f'{u:08x}\n' for u in cases))
    (out/'inputs.json').write_text(json.dumps([f'0x{u:08x}' for u in cases],indent=2)+'\n')
    # An exact RTL snapshot plus a standalone printing TB make each run reproducible.
    backup=out/'exp_fp32.v'
    shutil.copyfile(rtl,backup)
    snap,monitors=build_print_code(signals)
    (out/'debug_snapshot.svh').write_text(snap)
    (out/'debug_monitors.svh').write_text(monitors)
    tb=(ROOT/'tb/tb_exp_fp32_debug.sv').read_text()
    full=tb.replace('`include "debug_snapshot.svh"',snap).replace('`include "debug_monitors.svh"',monitors)
    fullpath=out/'tb_exp_fp32_debug_full.sv'; fullpath.write_text(full)
    binary=out/'debug.vvp'
    run_logged([tool('iverilog','IVERILOG'),'-g2012','-Wall','-s','tb_exp_fp32_debug','-o',str(binary),str(backup),str(fullpath)],out/'compile.log')
    run_logged([tool('vvp','VVP'),str(binary),'+inputs='+str(out/'inputs.hex'),
                '+snapshots='+str(out/'snapshots_raw.csv'),'+events='+str(out/'events_raw.csv')],out/'simulation.log')
    summary=convert_outputs(out,signals,cases,sha)
    print(f"Dumped {summary['cases']} cases, {summary['signals']} signals, {summary['signal_updates']} updates")
    print('Snapshots:',out/'signals.csv')
    print('Updates:  ',out/'signal_updates.csv')
    if summary['model_mismatches']:
        raise RuntimeError(f"{summary['model_mismatches']} RTL/model mismatches; CSV files retained")

if __name__=='__main__':
    try:
        main()
    except (ValueError,RuntimeError,OSError,json.JSONDecodeError) as e:
        print('ERROR:',e,file=sys.stderr)
        sys.exit(1)
