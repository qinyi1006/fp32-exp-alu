"""Regression checks for the user-input interface and CSV trace consistency."""
import csv
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('debug_exp',ROOT/'scripts/debug_exp.py')
debug=importlib.util.module_from_spec(spec); spec.loader.exec_module(debug)

class DebugInterfaceTests(unittest.TestCase):
    def test_unsupported_signal_declarations_fail_closed(self):
        source=(ROOT/'rtl/exp_fp32.v').read_text()
        for decl in ('wire a, b;', 'wire a=1, b=0;', 'wire [WIDTH-1:0] a;', 'logic a;'):
            with self.assertRaises(ValueError):
                debug.discover_signals(source.replace('endmodule',decl+'\nendmodule'))

    def test_input_formats_and_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'inputs.json'
            p.write_text(json.dumps(['0x3f800000', "32'hbf80_0000", '00000000', 0xffffffff,0]))
            self.assertEqual(debug.read_inputs(p),[0x3f800000,0xbf800000,0,0xffffffff,0])
            for bad in [[],{},[True],[-1],[2**32],[1.0],['xyz'],['0x100000000']]:
                p.write_text(json.dumps(bad))
                with self.assertRaises(ValueError): debug.read_inputs(p)

    def test_all_signals_events_duplicates_and_out_of_range(self):
        with tempfile.TemporaryDirectory(prefix='exp debug ') as tmp:
            tmp=Path(tmp); inputs=tmp/'input array.json'; out=tmp/'output csv'
            cases=[0,0x80000000,0xc2800000,0x42800000,0x3f800000,
                   0x3f800000,0x7fc00001,0x7f800000,0xff800000,0x3d314b3f]
            inputs.write_text(json.dumps(cases))
            original=(ROOT/'rtl/exp_fp32.v').read_bytes()
            result=subprocess.run([sys.executable,str(ROOT/'scripts/debug_exp.py'),
                                   '--inputs',str(inputs),'--out',str(out)],
                                   text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            self.assertEqual(result.returncode,0,result.stdout)
            self.assertEqual((ROOT/'rtl/exp_fp32.v').read_bytes(),original)
            self.assertEqual((out/'exp_fp32.v').read_bytes(),original)
            manifest=json.loads((out/'signals_manifest.json').read_text())['signals']
            names={s['name'] for s in manifest}
            self.assertEqual(len(names),93)
            self.assertTrue({'lut_0_0','lut_0_31','lut_5_0','negative_y_q24','log_product','output_exp'}<=names)
            with (out/'signals.csv').open() as f: rows=list(csv.DictReader(f))
            with (out/'signal_updates.csv').open() as f: events=list(csv.DictReader(f))
            self.assertEqual(len(rows),len(cases))
            self.assertEqual([int(r['x'],16) for r in rows],cases)
            self.assertTrue(names <= set(rows[0]))
            widths={s['name']:s['hex_digits'] for s in manifest}
            for row in rows:
                for name in names:
                    self.assertRegex(row[name],r'^0x[0-9a-fxz]{'+str(widths[name])+r'}$')
            self.assertEqual(rows[0]['y'],'0x3f800000')
            self.assertEqual(rows[1]['y'],'0x3f800000')
            self.assertEqual(rows[-1]['y'],'0x3f85a96e')
            for i in (6,7,8):
                self.assertEqual(rows[i]['reference_valid'],'0x0')
                self.assertEqual(rows[i]['model_expected'],'0xxxxxxxxx')
            for i in (0,1,2,3,4,5,9): self.assertEqual(rows[i]['model_match'],'0x1')
            self.assertEqual(rows[4]['y'],rows[5]['y'])
            # Replay every logged signal update in the emitted order. The last
            # observed values must agree with the stable snapshot of that case.
            state={}
            pos=0
            for i,row in enumerate(rows):
                start=pos
                while pos<len(events) and int(events[pos]['case_id'],16)==i:
                    e=events[pos]
                    self.assertEqual(int(e['update_seq'],16),pos+1)
                    self.assertEqual(int(e['input_x'],16),cases[i])
                    self.assertEqual(int(e['time_ns'],16),i+1)
                    state[e['signal']]=e['value']; pos+=1
                for name,v in state.items(): self.assertEqual(v,row[name],(i,name,v,row[name]))
                if i==5: self.assertEqual(pos,start,'Identical adjacent inputs must have no DUT changes')
                state.update({name:row[name] for name in names})
            self.assertEqual(pos,len(events))
            summary=json.loads((out/'summary.json').read_text())
            self.assertEqual(summary['model_mismatches'],0)
            self.assertEqual(summary['valid_reference_cases'],7)
            self.assertEqual(summary['signal_updates'],len(events))

if __name__=='__main__': unittest.main()
