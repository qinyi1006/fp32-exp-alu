`timescale 1ns/1ps
// Verification only: original-model vectors, full-bit-pattern samples, and
// every FP32 magnitude from 64 through 128 with both signs.
module tb_exp_fp32_v2;
    reg [31:0] x, expected, u;
    wire [31:0] y, original_y;
    exp_fp32_v2 dut(.x(x), .y(y));
    exp_fp32 original(.x(x), .y(original_y));
    integer fd, csv_fd, summary_fd, status, s, directed_count;
    integer vector_count, dense_count, total_count;
    integer core_count, high_count, low_count, nan_count;
    reg [4095:0] vector_path, csv_path, summary_path;
    reg [31:0] worst_x;
    real unused_reference, input_real, reference, relerr, worst_error;

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

    task check_output;
        begin
            total_count=total_count+1;
            if ((^y)===1'bx) $fatal(1,"Unknown output x=%h y=%h",x,y);
            // The computational core must remain unchanged even when bypassed.
            if (dut.core_y !== original_y)
                $fatal(1,"Original datapath changed x=%h core=%h original=%h",x,dut.core_y,original_y);
            relerr=-1.0;
            if (x[30:23]==255 && x[22:0]!=0) begin
                nan_count=nan_count+1;
                if (y!==32'h7fc00000) $fatal(1,"NaN handling x=%h y=%h",x,y);
            end else if (x==32'h7f800000) begin
                high_count=high_count+1;
                if (y!==32'h7f800000) $fatal(1,"+Inf handling y=%h",y);
            end else if (x==32'hff800000) begin
                low_count=low_count+1;
                if (y!==32'h00000000) $fatal(1,"-Inf handling y=%h",y);
            end else begin
                // Independent numerical comparison, not the RTL bit comparator.
                input_real=fp32_real(x);
                if (input_real>88.72283172607421875) begin
                    high_count=high_count+1;
                    if (y!==32'h7f800000) $fatal(1,"Upper saturation x=%h y=%h",x,y);
                end else if (input_real < -87.3365478515625) begin
                    low_count=low_count+1;
                    if (y!==32'h00000000) $fatal(1,"Lower flush x=%h y=%h",x,y);
                end else begin
                    core_count=core_count+1;
                    if (y!==original_y) $fatal(1,"In-range output changed x=%h",x);
                    if (y[30:23]==255) $fatal(1,"Nonfinite in-range output x=%h",x);
                    reference=$exp(input_real);
                    relerr=(fp32_real(y)-reference)/reference;
                    if (relerr<0.0) relerr=-relerr;
                    if (!(relerr<=1.0e-5)) $fatal(1,"Accuracy x=%h y=%h error=%e",x,y,relerr);
                    if (relerr>worst_error) begin worst_error=relerr; worst_x=x; end
                end
            end
        end
    endtask

    initial begin
        if (!$value$plusargs("vectors=%s",vector_path)) $fatal(1,"Missing vectors");
        if (!$value$plusargs("csv=%s",csv_path)) $fatal(1,"Missing CSV path");
        if (!$value$plusargs("summary=%s",summary_path)) $fatal(1,"Missing summary");
        if (!$value$plusargs("directed=%d",directed_count)) $fatal(1,"Missing directed count");
        fd=$fopen(vector_path,"r"); csv_fd=$fopen(csv_path,"w");
        if (!fd || !csv_fd) $fatal(1,"Cannot open vectors/CSV");
        $fdisplay(csv_fd,"input_hex,output_hex,expected_hex,relative_error_in_range");
        vector_count=0; dense_count=0; total_count=0;
        core_count=0; high_count=0; low_count=0; nan_count=0;
        worst_error=0.0; worst_x=0;
        status=$fscanf(fd,"%h %h %e\n",x,expected,unused_reference);
        while (status==3) begin
            #1;
            if (y!==expected) $fatal(1,"Model mismatch x=%h y=%h expected=%h",x,y,expected);
            check_output;
            if (vector_count<directed_count)
                $fdisplay(csv_fd,"0x%08h,0x%08h,0x%08h,%.17e",x,y,expected,relerr);
            vector_count=vector_count+1;
            status=$fscanf(fd,"%h %h %e\n",x,expected,unused_reference);
        end
        if (!$feof(fd) || vector_count==0) $fatal(1,"Invalid/empty vectors");
        $fclose(fd); $fclose(csv_fd);
        $display("PASS vectors=%0d",vector_count); $fflush();
        for (u=32'h42800000;u<=32'h43000000;u=u+1) begin
            for (s=0;s<2;s=s+1) begin
                x=u | (s ? 32'h80000000 : 32'h00000000);
                #1;
                check_output;
                dense_count=dense_count+1;
            end
            if (u[19:0]==0) begin
                $display("PROGRESS abs(x)=%.0f dense=%0d",fp32_real(u),dense_count);
                $fflush();
            end
        end
        summary_fd=$fopen(summary_path,"w");
        if (!summary_fd) $fatal(1,"Cannot open summary");
        $fdisplay(summary_fd,"{\"vector_cases\":%0d,\"dense_cases\":%0d,\"total_cases\":%0d,",vector_count,dense_count,total_count);
        $fdisplay(summary_fd,"\"in_range\":%0d,\"saturated_high\":%0d,\"flushed_low\":%0d,\"nan_cases\":%0d,",core_count,high_count,low_count,nan_count);
        $fdisplay(summary_fd,"\"max_in_range_relative_error\":%.17e,\"worst_input_hex\":\"%08h\"}",worst_error,worst_x);
        $fclose(summary_fd);
        $display("PASS total=%0d dense=%0d max_relative_error=%.12e worst=%h",total_count,dense_count,worst_error,worst_x);
        $finish;
    end
endmodule
