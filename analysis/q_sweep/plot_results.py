#!/usr/bin/env python3
"""Plot exhaustive model maxima, derive bounds, and verify worst points at 70 digits."""
import csv, json, math, os, struct
from decimal import Decimal, localcontext
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'.tools/mplconfig'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager, ticker
HERE=Path(__file__).resolve().parent
font=Path('/System/Library/Fonts/Hiragino Sans GB.ttc')
if font.exists():
    font_manager.fontManager.addfont(str(font))
    plt.rcParams['font.family']=[font_manager.FontProperties(fname=str(font)).get_name(),'DejaVu Sans']
plt.rcParams.update({'font.size':11,'axes.spines.top':False,'axes.spines.right':False,
                     'axes.unicode_minus':False,'font.weight':300,'axes.labelweight':300,'svg.fonttype':'path'})

def bound(fx,fy,fc):
    qx=2.0**-fx; qy=2.0**-fy; l=math.log(2)
    c=round(2.0**fc/l)/2.0**fc
    d=qx/l+64*abs(c-1/l)+qy
    er=math.expm1(l*d)
    h=(1/32)*(qy/2+(1/32)*qy/2+qy)+qy
    b=(l/32)**3/6
    p=1+l/32+(l/32)**2/2
    a=b+h+qy/2*(p+h)+qy
    rounding=0 if fy<=23 else 2**-24
    return er+(1+er)*(a+rounding)

def fvalue(h): return struct.unpack('>f',bytes.fromhex(h))[0]
rows=list(csv.DictReader((HERE/'results.csv').open()))
for r in rows:
    for k in ('input_fraction_bits','internal_fraction_bits','log_coefficient_fraction_bits','endpoint_checks','quantization_cells','dense_positive_values'): r[k]=int(r[k])
    r['max_relative_error']=float(r['max_relative_error']); r['worst_x']=float(r['worst_x'])
    r['conservative_bound']=bound(r['input_fraction_bits'],r['internal_fraction_bits'],r['log_coefficient_fraction_bits'])
    assert r['max_relative_error']<=r['conservative_bound']
    with localcontext() as ctx:
        ctx.prec=70
        x=Decimal.from_float(fvalue(r['worst_input_hex']))
        y=Decimal.from_float(fvalue(r['worst_output_hex']))
        ref=x.exp(); err=abs(y-ref)/ref
        r['worst_error_decimal70']=str(err)
        assert abs(float(err)-r['max_relative_error'])<4e-16

families=['datapath','uniform','input_only']
colors={'datapath':'#1565C0','uniform':'#C75D28','input_only':'#16836D'}
labels={'datapath':'主数据通路 QF；log₂(e) 保持 Q30',
        'uniform':'统一 QF；包括 log₂(e) 常数',
        'input_only':'仅输入量化 QF；后续保持当前 Q24 / Q30'}
series={s:sorted([r for r in rows if r['series']==s],key=lambda r:r['input_fraction_bits']) for s in families}
first={s:next(r['input_fraction_bits'] for r in series[s] if r['max_relative_error']<=1e-5) for s in families}
summary={'domain':'All finite FP32 inputs in [-64,64], both signed zeros',
         'input_bit_patterns_covered_per_configuration':2*(0x42800000+1),
         'method':'Constant-output input-quantization cells: endpoints, then dense FP32 enumeration',
         'first_passing_fraction_bits_in_sweep':first,'data':rows}
(HERE/'results.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')

fig,(ax,detail)=plt.subplots(1,2,figsize=(15,7.2),gridspec_kw={'width_ratios':[1.45,1]})
fig.patch.set_facecolor('#FAFBFD')
for a in (ax,detail):
    a.set_facecolor('white'); a.set_yscale('log'); a.grid(True,which='major',color='#DFE4EB',linewidth=.8)
    a.axhline(1e-5,color='#B52737',linestyle='--',linewidth=1.5,zorder=2)
    a.set_xlabel('小数位数 F（QF）',labelpad=10)
    a.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v,pos: f'{v:.0e}'))
    a.yaxis.set_minor_formatter(ticker.NullFormatter())
ax.set_ylabel('最大相对误差  |输出 - exp(x)| / exp(x)',labelpad=10)
for s in families:
    rr=series[s]; xs=[r['input_fraction_bits'] for r in rr]; ys=[r['max_relative_error'] for r in rr]
    ax.plot(xs,ys,'o-',color=colors[s],label=labels[s],linewidth=2.1,markersize=4.5)
ax.set_xlim(11.7,26.4); ax.set_xticks(range(12,27,2)); ax.set_ylim(1.2e-6,7e-3)
ax.set_title('全区间最大误差：三种降位宽方式',loc='left',fontsize=15,pad=16)
ax.legend(loc='upper right',frameon=True,facecolor='white',edgecolor='#DFE4EB',fontsize=9.8)
ax.text(12.2,1.14e-5,'精度要求 1e-5',color='#B52737',fontsize=10)
rr=series['datapath']; xs=[r['input_fraction_bits'] for r in rr]
detail.plot(xs,[r['conservative_bound'] for r in rr],'--',color='#75859A',label='解析保守上界',linewidth=1.8)
detail.plot(xs,[r['max_relative_error'] for r in rr],'o-',color=colors['datapath'],label='覆盖全部 FP32 输入的模型最大值',linewidth=2)
detail.axhline((math.log(2)/32)**3/6,color='#89929E',linestyle=':',linewidth=1.2,label='二次式 Taylor 余项上界 ≈ 1.69e-6')
detail.set_xlim(17.6,26.4); detail.set_ylim(1.35e-6,2.3e-5); detail.set_xticks(range(18,27))
detail.yaxis.set_major_locator(ticker.FixedLocator([2e-6,3e-6,4e-6,6e-6,1e-5,2e-5]))
detail.set_title('主数据通路：达标点与误差平台',loc='left',fontsize=15,pad=16)
for f,label,xytext in [(19,'Q19: 8.994e-6',(19.6,1.48e-5)),(20,'Q20: 5.347e-6',(21.0,6.9e-6)),(24,'Q24: 1.926e-6',(22.3,3.5e-6))]:
    y=next(r['max_relative_error'] for r in rr if r['input_fraction_bits']==f)
    detail.annotate(label,xy=(f,y),xytext=xytext,fontsize=10,color=colors['datapath'],arrowprops={'arrowstyle':'-','color':colors['datapath'],'lw':.9})
detail.legend(loc='upper right',bbox_to_anchor=(1,-.18),frameon=False,fontsize=9.1)
fig.suptitle('FP32 exp(x)：Q 格式如何影响精度',x=.07,ha='left',fontsize=22,fontweight='bold',y=.98)
fig.text(.07,.90,'固定 32 项表、二次多项式、FP32 输出与舍入规则；输入范围 [-64, 64]',fontsize=11,color='#526175')
fig.text(.07,.035,'曲线来自整数模型的量化区间端点搜索与 FP32 枚举；非随机抽样。各 QF 尚未分别生成或综合 RTL。',fontsize=10,color='#526175')
fig.subplots_adjust(left=.07,right=.98,top=.82,bottom=.23,wspace=.25)
fig.savefig(HERE/'q_error_curves.png',dpi=180,facecolor=fig.get_facecolor())
fig.savefig(HERE/'q_error_curves.svg',facecolor=fig.get_facecolor())
plt.close(fig)
print(json.dumps({'first_passing':first,'coverage':summary['input_bit_patterns_covered_per_configuration'],'files':['q_error_curves.png','q_error_curves.svg','results.csv','results.json']},ensure_ascii=False,indent=2))
for r in series['datapath']:
    if r['input_fraction_bits'] in (18,19,20,24): print(r['input_fraction_bits'],r['max_relative_error'],r['conservative_bound'])
