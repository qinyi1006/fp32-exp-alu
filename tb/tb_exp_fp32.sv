`timescale 1ns/1ps
module tb_exp_fp32;
    reg [31:0] x;
    wire [31:0] y;
    reg [31:0] expected;
    reg [31:0] worst_x;
    real reference, actual, relerr, worst_error;
    integer fd, count, status;
    reg [4095:0] vector_path;
    exp_fp32 dut(.x(x), .y(y));

    // Portable binary32 decode; avoids simulator-specific shortreal support.
    function real fp32_real(input reg [31:0] u);
        real m;
        integer exponent;
        begin
            exponent = u[30:23];
            m = u[22:0];
            if (exponent == 0) fp32_real = m * (2.0 ** (-149));
            else fp32_real = (8388608.0 + m) * (2.0 ** (exponent-150));
            if (u[31]) fp32_real = -fp32_real;
        end
    endfunction

    initial begin
        if (!$value$plusargs("vectors=%s", vector_path)) vector_path = "build/vectors.txt";
        fd = $fopen(vector_path, "r");
        if (fd == 0) $fatal(1, "Cannot open vector file: %0s", vector_path);
        count = 0;
        worst_error = 0.0;
        worst_x = 0;
        // Each input follows the previous one directly. No clock/handshake.
        status = $fscanf(fd, "%h %h %e\n", x, expected, reference);
        while (status == 3) begin
            #1;
            if (y !== expected)
                $fatal(1, "Bit mismatch x=%h RTL=%h model=%h", x, y, expected);
            actual = fp32_real(y);
            relerr = (actual-reference)/reference;
            if (relerr < 0) relerr = -relerr;
            if (!(relerr <= 1.0e-5))
                $fatal(1, "Accuracy failure x=%h y=%h relerr=%e", x, y, relerr);
            if (relerr > worst_error) begin
                worst_error = relerr;
                worst_x = x;
            end
            count = count + 1;
            status = $fscanf(fd, "%h %h %e\n", x, expected, reference);
        end
        if (!$feof(fd)) $fatal(1, "Malformed vector file after %0d vectors", count);
        if (count == 0) $fatal(1, "No test vectors");
        $fclose(fd);
        $display("PASS: %0d vectors, max_relative_error=%.12e, worst_x=%h (%0.12f)",
                 count, worst_error, worst_x, fp32_real(worst_x));
        $finish;
    end
endmodule
