`timescale 1ns/1ps
module tb_exp_fp32_v3;
    reg [31:0] x, expected, u;
    wire [31:0] y, v2_y;
    exp_fp32_v3 dut(.x(x), .y(y));
    exp_fp32_v2 previous(.x(x), .y(v2_y));
    integer fd, csv_fd, summary_fd, status, s, i, directed_count;
    integer vectors, dense, total, normals, subnormals, highs, lows, nans;
    integer k_int, rounded_units, golden_units, ulp_distance, max_ulp_distance, golden_mismatches;
    reg [4095:0] vector_path, csv_path, summary_path;
    real unused_reference, input_real, reference, actual, relative_error;
    real unrounded, algorithm_error, units, model_units, error_units;
    real worst[0:3];
    reg [31:0] worst_x[0:3], worst_y[0:3];
    reg [191:0] metric[0:3];
    integer pack_count, pack_shift, tie_case, pack_k;
    reg [24:0] pack_m;
    reg [8:0] pack_k_bits;
    reg [63:0] pack_divisor, pack_q, pack_r, pack_expected;

    function real fp32_real(input reg [31:0] v);
        integer e;
        real m;
        begin
            e=v[30:23]; m=v[22:0];
            if (e==0) fp32_real=m*(2.0**(-149));
            else fp32_real=(8388608.0+m)*(2.0**(e-150));
            if (v[31]) fp32_real=-fp32_real;
        end
    endfunction

    task record(input integer index, input real error_value);
        begin
            if (error_value>worst[index]) begin
                worst[index]=error_value; worst_x[index]=x; worst_y[index]=y;
            end
        end
    endtask

    task check_output;
        begin
            total=total+1; relative_error=-1.0;
            if ((^y)===1'bx) $fatal(1,"Unknown output x=%h y=%h",x,y);
            if (dut.mant_q24!==previous.mant_q24 || dut.y_q24[31:0]!==previous.y_q24)
                $fatal(1,"Unintended approximation change x=%h",x);
            if (!x[31] && y!==v2_y) $fatal(1,"Positive behavior changed x=%h y=%h v2=%h",x,y,v2_y);
            if (x[30:23]==255 && x[22:0]!=0) begin
                nans=nans+1;
                if (y!==32'h7fc00000) $fatal(1,"NaN handling x=%h",x);
            end else if (x==32'h7f800000) begin
                highs=highs+1;
                if (y!==32'h7f800000) $fatal(1,"+Inf handling");
            end else if (x==32'hff800000) begin
                lows=lows+1;
                if (y!==0) $fatal(1,"-Inf handling");
            end else begin
                input_real=fp32_real(x);
                if (input_real>88.72283172607421875) begin
                    highs=highs+1;
                    if (y!==32'h7f800000) $fatal(1,"Upper saturation x=%h",x);
                end else if (input_real < -103.2789306640625) begin
                    lows=lows+1;
                    if (y!==0) $fatal(1,"Lower flush x=%h y=%h",x,y);
                end else begin
                    if (y[31] || y[30:23]==255 || y==0) $fatal(1,"Invalid active-range output x=%h y=%h",x,y);
                    if (input_real>=-87.33654022216796875 && y!==v2_y)
                        $fatal(1,"Normal-range V2 behavior changed x=%h",x);
                    k_int=dut.k;
                    if (k_int>=256) k_int=k_int-512;
                    if (k_int < -150 || k_int > 127) $fatal(1,"Exponent range x=%h k=%0d",x,k_int);
                    reference=$exp(input_real); actual=fp32_real(y);
                    unrounded=dut.mant_q24*(2.0**(k_int-24));
                    algorithm_error=(unrounded-reference)/reference;
                    if (algorithm_error<0) algorithm_error=-algorithm_error;
                    if (!(algorithm_error<=1e-5)) $fatal(1,"Approximation error x=%h error=%e",x,algorithm_error);
                    record(3,algorithm_error);
                    relative_error=(actual-reference)/reference;
                    if (relative_error<0) relative_error=-relative_error;
                    if (reference >= (2.0**(-126))) begin
                        normals=normals+1;
                        if (!(relative_error<=1e-5)) $fatal(1,"Normal accuracy x=%h error=%e",x,relative_error);
                        record(0,relative_error);
                    end else begin
                        subnormals=subnormals+1;
                        units=reference*(2.0**149);
                        error_units=(actual-reference)*(2.0**149);
                        if (error_units<0) error_units=-error_units;
                        if (!(error_units<=0.500001+1e-5*units))
                            $fatal(1,"Subnormal error bound x=%h error_ulp=%e",x,error_units);
                        // Powers-of-two scaling of a 25-bit integer is exact in binary64.
                        // This checks the RTL's guard/sticky logic by an independent method.
                        model_units=dut.mant_q24*(2.0**(k_int+125));
                        rounded_units=$rtoi(model_units);
                        if (model_units-rounded_units>0.5 ||
                            (model_units-rounded_units==0.5 && (rounded_units & 1)))
                            rounded_units=rounded_units+1;
                        if (y!==rounded_units) $fatal(1,"Subnormal RNE x=%h y=%h expected=%h",x,y,rounded_units);
                        golden_units=$rtoi(units);
                        if (units-golden_units>0.5 || (units-golden_units==0.5 && (golden_units & 1)))
                            golden_units=golden_units+1;
                        ulp_distance=(y>golden_units) ? y-golden_units : golden_units-y;
                        if (ulp_distance>0) golden_mismatches=golden_mismatches+1;
                        if (ulp_distance>max_ulp_distance) max_ulp_distance=ulp_distance;
                        record(1,relative_error); record(2,error_units);
                    end
                end
            end
        end
    endtask

    initial begin
        if (!$value$plusargs("vectors=%s",vector_path)) $fatal(1,"Missing vectors");
        if (!$value$plusargs("csv=%s",csv_path)) $fatal(1,"Missing CSV");
        if (!$value$plusargs("summary=%s",summary_path)) $fatal(1,"Missing summary");
        if (!$value$plusargs("directed=%d",directed_count)) $fatal(1,"Missing directed count");
        vectors=0; dense=0; total=0; normals=0; subnormals=0; highs=0; lows=0; nans=0;
        max_ulp_distance=0; golden_mismatches=0; pack_count=0;
        metric[0]="normal"; metric[1]="subnormal"; metric[2]="subnormal_ulp"; metric[3]="algorithm";
        for (i=0;i<4;i=i+1) begin worst[i]=-1.0; worst_x[i]=0; worst_y[i]=0; end
        // Force only the packer's inputs for directed ties/carry unit checks.
        // These are reported separately from real x-driven RTL cases.
        x=0;
        force dut.mant_q24=pack_m;
        force dut.k=pack_k_bits;
        for (pack_shift=1;pack_shift<=25;pack_shift=pack_shift+1) begin
            pack_k=-125-pack_shift; pack_k_bits=pack_k;
            pack_divisor=64'd1 << pack_shift;
            for (tie_case=0;tie_case<8;tie_case=tie_case+1) begin
                case (tie_case)
                    0: pack_m=25'h1000000;
                    1: pack_m=25'h1ffffff;
                    2: pack_m=25'h1fffffe;
                    3: pack_m=25'h1000000 | (pack_divisor/2);
                    4: pack_m=25'h1000000 | ((pack_divisor/2)-1);
                    5: pack_m=25'h1000000 | ((pack_divisor/2)+1);
                    6: pack_m=25'h1ffffff ^ (pack_divisor/2);
                    7: pack_m=25'h1000000 | (pack_divisor/2) | pack_divisor;
                endcase
                #1;
                pack_q=pack_m/pack_divisor; pack_r=pack_m%pack_divisor;
                pack_q=pack_q+((pack_r>pack_divisor/2) || ((pack_r==pack_divisor/2) && pack_q[0]));
                if (pack_shift==1) begin
                    if (pack_q>=64'h1000000) pack_expected=32'h01000000;
                    else pack_expected=32'h00800000 | (pack_q & 64'h7fffff);
                end else pack_expected=pack_q;
                if (y!==pack_expected[31:0]) $fatal(1,"Packer check shift=%0d mant=%h y=%h expected=%h",pack_shift,pack_m,y,pack_expected);
                pack_count=pack_count+1;
            end
        end
        release dut.mant_q24; release dut.k;
        x=32'h3f800000; #1;
        fd=$fopen(vector_path,"r"); csv_fd=$fopen(csv_path,"w");
        if (!fd || !csv_fd) $fatal(1,"Cannot open vectors/CSV");
        $fdisplay(csv_fd,"input_hex,output_hex,expected_hex,relative_error_in_range");
        status=$fscanf(fd,"%h %h %e\n",x,expected,unused_reference);
        while (status==3) begin
            #1;
            if (y!==expected) $fatal(1,"Model mismatch x=%h y=%h expected=%h",x,y,expected);
            check_output;
            if (vectors<directed_count) $fdisplay(csv_fd,"0x%08h,0x%08h,0x%08h,%.17e",x,y,expected,relative_error);
            vectors=vectors+1;
            status=$fscanf(fd,"%h %h %e\n",x,expected,unused_reference);
        end
        if (!$feof(fd) || vectors==0) $fatal(1,"Invalid vectors");
        $fclose(fd); $fclose(csv_fd);
        $display("PASS vectors=%0d packer_unit_cases=%0d",vectors,pack_count); $fflush();
        for (u=32'h42800000;u<=32'h43000000;u=u+1) begin
            for (s=0;s<2;s=s+1) begin
                x=u | (s ? 32'h80000000 : 32'h00000000);
                #1; check_output; dense=dense+1;
            end
            if (u[19:0]==0) begin
                $display("PROGRESS abs(x)=%.0f dense=%0d",fp32_real(u),dense); $fflush();
            end
        end
        summary_fd=$fopen(summary_path,"w");
        if (!summary_fd) $fatal(1,"Cannot open summary");
        $fdisplay(summary_fd,"{\"vector_cases\":%0d,\"dense_cases\":%0d,\"total_cases\":%0d,\"packer_unit_cases\":%0d,",vectors,dense,total,pack_count);
        $fdisplay(summary_fd,"\"normal_cases\":%0d,\"subnormal_cases\":%0d,\"high_cases\":%0d,\"low_cases\":%0d,\"nan_cases\":%0d,",normals,subnormals,highs,lows,nans);
        for (i=0;i<4;i=i+1) begin
            $fdisplay(summary_fd,"\"max_%0s_error\":%.17e,\"worst_%0s_input\":\"%08h\",\"worst_%0s_output\":\"%08h\",",metric[i],worst[i],metric[i],worst_x[i],metric[i],worst_y[i]);
        end
        $fdisplay(summary_fd,"\"max_subnormal_ulp_distance\":%0d,\"subnormal_math_golden_mismatches\":%0d}",max_ulp_distance,golden_mismatches);
        $fclose(summary_fd);
        $display("PASS total=%0d dense=%0d normal_relative_error=%e subnormal_relative_error=%e max_subnormal_ulp_distance=%0d",total,dense,worst[0],worst[1],max_ulp_distance);
        $finish;
    end
endmodule
