// Exact search over FP32 inputs using constant-output quantization cells.
// Analysis only; this C file is not intended for TIE translation.
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <inttypes.h>

typedef struct { int fx, fy, fc; uint64_t clog,c1,c2,table[32]; } Config;
typedef struct { double err; uint32_t in,out; uint64_t checks; } Worst;
static uint32_t bits(float f) { uint32_t u; memcpy(&u,&f,4); return u; }
static float value(uint32_t u) { float f; memcpy(&f,&u,4); return f; }
static Config config(int fx,int fy,int fc) {
    Config c={.fx=fx,.fy=fy,.fc=fc}; double q=ldexp(1.0,fy),l=log(2.0);
    c.clog=(uint64_t)llrint(ldexp(1.0,fc)/l);
    c.c1=(uint64_t)llrint(l*q); c.c2=(uint64_t)llrint(l*l*q/2);
    for(int j=0;j<32;j++) c.table[j]=(uint64_t)llrint(exp2(j/32.0)*q);
    return c;
}
static uint32_t pack(uint64_t m,int fy,int k) {
    uint64_t s;
    if(fy<=23) s=m<<(23-fy);
    else {
        int shift=fy-23; uint64_t remainder=m&((UINT64_C(1)<<shift)-1);
        uint64_t half=UINT64_C(1)<<(shift-1);
        s=(m>>shift)+(remainder>half || (remainder==half && ((m>>shift)&1)));
    }
    if(s>=(UINT64_C(1)<<24)) { s>>=1; k++; }
    return ((uint32_t)(k+127)<<23) | ((uint32_t)s&0x7fffff);
}
static uint32_t model_y(int64_t y,const Config *c) {
    // Explicit floor division; avoid relying on right shift of negative C values.
    uint64_t scale=UINT64_C(1)<<c->fy;
    int64_t k=y>=0 ? y/(int64_t)scale : -(((-y)+(int64_t)scale-1)/(int64_t)scale);
    uint64_t f=(uint64_t)(y-k*(int64_t)scale);
    int j=(int)(f>>(c->fy-5)); uint64_t r=f&((scale>>5)-1);
    uint64_t t=c->c1+((r*c->c2)>>c->fy);
    uint64_t h=(r*t)>>c->fy;
    uint64_t m=c->table[j]+((c->table[j]*h)>>c->fy);
    return pack(m,c->fy,(int)k);
}
static void outputs(uint64_t mag,const Config *c,uint32_t *pos,uint32_t *neg) {
    // The logarithm coefficient precision is independently configured.
    uint64_t p=mag*c->clog;
    int shift=c->fx+c->fc-c->fy;
    int64_t a=(int64_t)(p>>shift);
    int sticky=(p&((UINT64_C(1)<<shift)-1))!=0;
    *pos=model_y(a,c); *neg=model_y(-a-sticky,c);
}
// Exported for cross-checks against the original independent Python model.
uint32_t q_model(uint32_t u,int fx,int fy,int fc) {
    Config c=config(fx,fy,fc); int e=(u>>23)&255;
    uint64_t sig=(u&0x7fffff)|(e?0x800000:0);
    int shift=e-150+fx;
    uint64_t mag=shift>=0 ? sig<<shift : (-shift>=64 ? 0 : sig>>(-shift));
    uint32_t pos,neg; outputs(mag,&c,&pos,&neg);
    return u>>31 ? neg : pos;
}
static void record(Worst *w,uint32_t u,uint32_t out,double ref) {
    double err=fabs((double)value(out)-ref)/ref;
    w->checks++;
    if(err>w->err) { w->err=err; w->in=u; w->out=out; }
}
static void endpoint(uint32_t u,uint32_t outputs_[3][2],Worst worst[3]) {
    double x=(double)value(u), rp=exp(x), rn=exp(-x);
    for(int c=0;c<3;c++) {
        record(&worst[c],u,outputs_[c][0],rp);
        record(&worst[c],u|0x80000000,outputs_[c][1],rn);
    }
}
static void sweep(int fx) {
    Config cs[3]={config(fx,fx,30),config(fx,24,30),config(fx,fx,fx)};
    Worst ws[3]={{0},{0},{0}};
    uint64_t end=UINT64_C(64)<<fx;
    uint64_t cells=end<(UINT64_C(1)<<24)?end:(UINT64_C(1)<<24);
    uint32_t outs[3][2];
    for(uint64_t n=0;n<cells;n++) {
        // For n<2^24, both cell boundaries n*2^-fx and (n+1)*2^-fx
        // are exactly representable FP32. The upper endpoint is prevfloat.
        uint32_t lo=bits((float)ldexp((double)n,-fx));
        uint32_t hi=bits((float)ldexp((double)(n+1),-fx))-1;
        for(int c=0;c<3;c++) outputs(n,&cs[c],&outs[c][0],&outs[c][1]);
        endpoint(lo,outs,ws);
        if(hi!=lo) endpoint(hi,outs,ws);
    }
    // Beyond 2^24 integer quanta, every FP32 number is a grid point and
    // spacing is >= one quantum. Enumerate each remaining FP32 magnitude.
    uint32_t start=bits((float)ldexp((double)cells,-fx));
    uint64_t dense=0;
    for(uint32_t u=start;u<=0x42800000;u++) {
        uint64_t mag=(uint64_t)ldexp((double)value(u),fx);
        for(int c=0;c<3;c++) outputs(mag,&cs[c],&outs[c][0],&outs[c][1]);
        endpoint(u,outs,ws); dense++;
    }
    for(int c=0;c<3;c++) {
        printf("%s,%d,%d,%d,%.17g,%.17g,%08x,%08x,%" PRIu64 ",%" PRIu64 ",%" PRIu64 "\n",
            (const char *[]){"datapath","input_only","uniform"}[c],fx,cs[c].fy,cs[c].fc,ws[c].err,(double)value(ws[c].in),
            ws[c].in,ws[c].out,ws[c].checks,cells,dense);
    }
    fflush(stdout); fprintf(stderr,"Q%d complete: datapath %.9g; input-only %.9g; uniform %.9g\n",fx,ws[0].err,ws[1].err,ws[2].err);
}
#ifndef MODEL_LIBRARY
int main(int argc,char **argv) {
    int lo=argc>1?atoi(argv[1]):12,hi=argc>2?atoi(argv[2]):26;
    if(lo<12||hi>26||lo>hi) return 2;
    puts("series,input_fraction_bits,internal_fraction_bits,log_coefficient_fraction_bits,max_relative_error,worst_x,worst_input_hex,worst_output_hex,endpoint_checks,quantization_cells,dense_positive_values");
    for(int f=lo;f<=hi;f++) sweep(f);
    return 0;
}
#endif
