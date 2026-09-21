#!/usr/bin/env python3
"""Independent Python checks for the C integer model and original Q24 RTL vectors."""
import ctypes, math, random, struct, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from verify_model import model as original_model, bits, value
lib=ctypes.CDLL(str(ROOT/'build/q_model.dylib'))
lib.q_model.argtypes=[ctypes.c_uint32,ctypes.c_int,ctypes.c_int,ctypes.c_int]
lib.q_model.restype=ctypes.c_uint32

def independent(u,fx,fy,fc):
    xq=math.trunc(math.ldexp(value(u),fx))
    c=round(math.ldexp(1.0,fc)/math.log(2))
    y=(xq*c)//(1<<(fx+fc-fy))
    k=y>>fy; f=y-(k<<fy); j=f>>(fy-5); r=f&((1<<(fy-5))-1)
    c1=round(math.log(2)*(1<<fy)); c2=round(math.log(2)**2/2*(1<<fy))
    t=c1+(r*c2>>fy); h=r*t>>fy; table=round(2**(j/32)*(1<<fy))
    m=table+(table*h>>fy)
    return bits(math.ldexp(m,k-fy))

count=0
with (ROOT/'build/vectors.txt').open() as f:
    for row in f:
        u,out,_=row.split()
        assert lib.q_model(int(u,16),24,24,30)==int(out,16)
        count+=1
print(f'Original Q24 RTL-validated vector matches: {count}')
rng=random.Random(921); checks=0
for fx in range(12,27):
    for fy,fc in {(fx,30),(24,30),(fx,fx)}:
        fixed=[0,0x80000000,1,0x80000001,bits(64),bits(-64)]
        for x in (2.0**-fx,2.0**(24-fx)):
            u=bits(x)
            fixed += [v|(s<<31) for v in (u-1,u,u+1) if v<=bits(64) for s in (0,1)]
        randoms=[rng.randrange(0x42800001)|(rng.randrange(2)<<31) for _ in range(10000)]
        for u in fixed+randoms:
            assert lib.q_model(u,fx,fy,fc)==independent(u,fx,fy,fc),(hex(u),fx,fy,fc)
            checks+=1
print(f'Parameterized independent cross-check: PASS ({checks} cases)')
