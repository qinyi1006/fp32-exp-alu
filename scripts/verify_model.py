#!/usr/bin/env python3
"""Bit-exact integer model, directed/random vectors, and conservative error bound."""
import argparse, math, random, struct, json
from pathlib import Path
Q = 1 << 24
LOG2E = round((1 / math.log(2)) * (1 << 30))
C1 = round(math.log(2) * Q)
C2 = round(math.log(2)**2 / 2 * Q)
TABLE = [round(2**(j / 32) * Q) for j in range(32)]
def bits(x):
    return struct.unpack('>I', struct.pack('>f', x))[0]
def value(u):
    return struct.unpack('>f', struct.pack('>I', u))[0]
def model(u):
    e = (u >> 23) & 255
    sig = (u & 0x7fffff) | (0x800000 if e else 0)
    mag = sig << (e-126) if e >= 126 else sig >> (126-e)
    xq = -mag if u >> 31 else mag
    yq = (xq * LOG2E) >> 30
    k = yq >> 24
    j = (yq >> 19) & 31
    r = yq & ((1 << 19)-1)
    t = C1 + ((r * C2) >> 24)
    h = (r * t) >> 24
    m = TABLE[j] + ((TABLE[j] * h) >> 24)
    # Round Q24 significand to Q23, ties to even.
    sig24 = (m >> 1) + ((m & 1) & ((m >> 1) & 1))
    carry = sig24 >> 24
    return ((k + 127 + carry) << 23) | ((sig24 >> carry) & 0x7fffff)
def bound():
    q = 1 / Q
    l = math.log(2)
    # x quantization; coefficient error; floor of log2-domain result.
    dy = (1/l)*q + 64*abs(LOG2E/(1<<30)-1/l) + q
    range_rel = math.expm1(l*dy)
    rmax = 1/32
    # Taylor remainder relative to exp(z) <= z^3/6.
    poly = (l*rmax)**3 / 6
    # c1,c2 rounded; inner product floor; outer product floor.
    h_abs = rmax*(q/2 + rmax*q/2 + q) + q
    # Table is rounded, final correction product is floored.
    approx_abs = poly + h_abs + q/2*(1 + l*rmax + (l*rmax)**2/2 + h_abs) + q
    # Q24->Q23 rounding absolute error <= 2^-24; significand >=1.
    total = range_rel + (1+range_rel)*(approx_abs+q)
    return dict(range_relative=range_rel, taylor_relative=poly,
                fixed_polynomial_absolute=h_abs, conservative_relative_bound=total)
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--output', default='build/vectors.txt')
    ap.add_argument('--random',type=int,default=200000)
    args=ap.parse_args()
    rng=random.Random(20260916)
    samples={0,0x80000000,bits(-64),bits(64)}
    # Adjacent FP32 values on both sides of every table/range boundary.
    for n in range(-2955,2956):
        u=bits(n*math.log(2)/32)
        for d in range(-4,5):
            v=u+d
            if 0<=v<=0xffffffff and math.isfinite(value(v)) and abs(value(v))<=64:
                samples.add(v)
    # Exponent transitions, subnormals, signed zeros, and tiny inputs.
    for e in range(134):
        for f in (0,1,2,0x3fffff,0x7ffffd,0x7ffffe,0x7fffff):
            for s in (0,1):
                u=(s<<31)|(e<<23)|f
                if abs(value(u))<=64: samples.add(u)
    for _ in range(args.random):
        samples.add(bits(rng.uniform(-64,64)))
        samples.add(rng.randrange(0x42800001) | (rng.randrange(2)<<31))
    worst=(0.0,0,0)
    path=Path(args.output); path.parent.mkdir(parents=True,exist_ok=True)
    ordered = sorted(samples)
    rng.shuffle(ordered)
    with path.open('w') as f:
        for u in ordered:
            x=value(u); ref=math.exp(x); out=model(u)
            err=abs(value(out)-ref)/ref
            if err>worst[0]: worst=(err,u,out)
            if not err<=1e-5: raise AssertionError((x,err))
            f.write(f'{u:08x} {out:08x} {ref:.17e}\n')
    report={'vectors':len(samples),'seed':20260916,'max_relative_error':worst[0],
            'worst_x':value(worst[1]), 'worst_input_hex':f'{worst[1]:08x}',
            'worst_output_hex':f'{worst[2]:08x}','constants':{'log2e':LOG2E,'c1':C1,'c2':C2},
            'bounds':bound()}
    assert report['bounds']['conservative_relative_bound']<1e-5
    path.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__': main()
