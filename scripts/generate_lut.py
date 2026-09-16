#!/usr/bin/env python3
"""Emit a balanced 32-to-1 ternary tree for the Q24 exp2 table."""
import math
for j in range(32):
    print(f'    wire [24:0] lut_0_{j} = 25\'d{round(2**(j/32)*(1<<24))};')
for level in range(1,6):
    for j in range(32>>level):
        print(f'    wire [24:0] lut_{level}_{j} = j[{level-1}] ? lut_{level-1}_{2*j+1} : lut_{level-1}_{2*j};')
print('    wire [24:0] table_q24 = lut_5_0;')
