`timescale 1ns/1ps
// Simulation only. Exhaust every FP32 magnitude in [64,128], both signs.
// No mathematical model substitutes for the DUT in this sweep.
module tb_range_boundary;
    reg [31:0] x;
    wire [31:0] y;
    exp_fp32 dut(.x(x), .y(y));
    reg [31:0] u, stop_bits;
    reg [31:0] first_bad_x [0:1];
    reg [31:0] first_bad_y [0:1];
    reg [31:0] last_good_x [0:1];
    reg [31:0] last_good_y [0:1];
    reg [31:0] worst_x [0:1];
    reg [31:0] worst_y [0:1];
    integer count [0:1];
    integer pass_count [0:1];
    integer pass_after_failure [0:1];
    integer seen_failure [0:1];
    real worst_error [0:1];
    real reference, actual, relerr, magnitude_real;
    integer s, good, fd;
    reg [4095:0] summary_path;

    function real fp32_real(input reg [31:0] v);
        real m;
        integer e;
        begin
            e = v[30:23];
            m = v[22:0];
            if (e == 0) fp32_real = m * (2.0 ** (-149));
            else fp32_real = (8388608.0 + m) * (2.0 ** (e-150));
            if (v[31]) fp32_real = -fp32_real;
        end
    endfunction

    initial begin
        if (!$value$plusargs("summary=%s", summary_path))
            summary_path = "build/range_boundary/sweep.json";
        // Override is useful only for development timing, not the final report.
        if (!$value$plusargs("stop=%h", stop_bits)) stop_bits = 32'h43000000;
        for (s=0; s<2; s=s+1) begin
            count[s]=0; pass_count[s]=0; pass_after_failure[s]=0;
            seen_failure[s]=0; worst_error[s]=0.0;
            first_bad_x[s]=0; first_bad_y[s]=0;
            last_good_x[s]=0; last_good_y[s]=0;
            worst_x[s]=0; worst_y[s]=0;
        end
        for (u=32'h42800000; u<=stop_bits; u=u+1) begin
            magnitude_real=fp32_real(u);
            for (s=0; s<2; s=s+1) begin
                x=u | (s ? 32'h80000000 : 32'h00000000);
                #1;
                reference=$exp(s ? -magnitude_real : magnitude_real);
                good=0;
                if ((^y) === 1'bx) $fatal(1,"Unknown output x=%h y=%h",x,y);
                // Exponent 255 is Inf/NaN, never a finite real value.
                if (y[30:23] != 8'hff) begin
                    actual=fp32_real(y);
                    relerr=(actual-reference)/reference;
                    if (relerr<0.0) relerr=-relerr;
                    good=(relerr<=1.0e-5);
                end
                count[s]=count[s]+1;
                if (good) begin
                    pass_count[s]=pass_count[s]+1;
                    if (seen_failure[s]) pass_after_failure[s]=pass_after_failure[s]+1;
                    else begin
                        last_good_x[s]=x; last_good_y[s]=y;
                        if (relerr>worst_error[s]) begin
                            worst_error[s]=relerr; worst_x[s]=x; worst_y[s]=y;
                        end
                    end
                end else if (!seen_failure[s]) begin
                    seen_failure[s]=1; first_bad_x[s]=x; first_bad_y[s]=y;
                    $display("FIRST FAILURE sign=%0d x=%h (%.15f) y=%h",s,x,fp32_real(x),y);
                end
            end
            if (u[19:0]==0) begin
                $display("PROGRESS magnitude=%.6f total_cases=%0d",magnitude_real,count[0]+count[1]);
                $fflush();
            end
        end
        fd=$fopen(summary_path,"w");
        if (!fd) $fatal(1,"Cannot open summary");
        $fdisplay(fd,"{\"start_bits\":\"42800000\",\"stop_bits\":\"%08h\",\"sides\":[",stop_bits);
        for (s=0; s<2; s=s+1) begin
            $fdisplay(fd,"{\"negative\":%0d,\"cases\":%0d,\"passes\":%0d,\"passes_after_first_failure\":%0d,",s,count[s],pass_count[s],pass_after_failure[s]);
            $fdisplay(fd,"\"last_good_input\":\"%08h\",\"last_good_output\":\"%08h\",\"first_bad_input\":\"%08h\",\"first_bad_output\":\"%08h\",",last_good_x[s],last_good_y[s],first_bad_x[s],first_bad_y[s]);
            $fdisplay(fd,"\"worst_prefix_relative_error\":%.17e,\"worst_prefix_input\":\"%08h\",\"worst_prefix_output\":\"%08h\"}",worst_error[s],worst_x[s],worst_y[s]);
            if (s==0) $fdisplay(fd,",");
        end
        $fdisplay(fd,"]}");
        $fclose(fd);
        $display("DONE: %0d RTL inputs, no sampling",count[0]+count[1]);
        $finish;
    end
endmodule
